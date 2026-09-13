"""The job worker (A05): claiming, leases, stalled-job recovery, and the two ways to
run it (embedded thread, separate process). Scripted models only; no live calls."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from helpers import FakeChat, action, call, drain, run
from policy_update.api import create_app
from policy_update.database import initialize_database
from policy_update.extraction import ModelError
from policy_update.models import Case, ProcessingJob
from policy_update.worker import Worker

REQUEST = "For DEMO-1001 please update Sam Taylor's email to sam.new@example.com."
EMAIL = {"email": "sam.new@example.com"}
EXPIRED = "2000-01-01T00:00:00+00:00"
FAR_FUTURE = "2999-01-01T00:00:00+00:00"


@pytest.fixture
def chat():
    return FakeChat()


@pytest.fixture
def app(tmp_path, chat):
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'worker.db'}")
    return create_app(url, model=None, agent_model=chat)


def intake(client, guest, **overrides):
    payload = {
        "broker_id": "broker-alex",
        "policy_number": "DEMO-1001",
        "original_request": REQUEST,
    }
    payload.update(overrides)
    response = client.post("/cases", headers=guest, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def queue(client, guest, case_id, route="process"):
    response = client.post(f"/cases/{case_id}/{route}", headers=guest)
    assert response.status_code == 202, response.text
    return response.json()


def detail(client, guest, case_id):
    return client.get(f"/cases/{case_id}", headers=guest).json()


def events(case, name):
    return [event for event in case["timeline"] if event["action"] == name]


def set_job(app, case_id, **values):
    with app.state.sessions.begin() as session:
        job = session.get(ProcessingJob, case_id)
        for key, value in values.items():
            setattr(job, key, value)


def dead_running_job(app, case_id, attempts=1):
    """A job whose worker died mid-run: still ``running``, lease long lapsed."""
    with app.state.sessions.begin() as session:
        session.add(
            ProcessingJob(
                case_id=case_id,
                workspace_id=session.get(Case, case_id).workspace_id,
                action="process",
                status="running",
                attempts=attempts,
                worker_id="host:1:dead",
                lease_expires_at=EXPIRED,
            )
        )


def wait_for_job(client, guest, case_id, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        case = detail(client, guest, case_id)
        if case["job"]["status"] not in {"queued", "running"}:
            return case
        time.sleep(0.05)
    raise AssertionError("The worker did not finish the job in time")


def test_exactly_one_worker_claims_a_queued_job(app, client, guest, chat):
    chat.decisions += [call("submit_for_approval", changes=EMAIL)]
    case_id = intake(client, guest)
    queue(client, guest, case_id)
    first = Worker(app.state.sessions, None, app.state.agent, worker_id="host:1:a")
    second = Worker(app.state.sessions, None, app.state.agent, worker_id="host:2:b")
    assert first.claim(case_id) is True
    assert second.claim(case_id) is False
    # The other worker sees nothing to do: the job is running under a live lease.
    assert second.run_pending() == []
    job = detail(client, guest, case_id)["job"]
    assert job["status"] == "running" and job["worker_id"] == "host:1:a"
    assert job["attempts"] == 1 and job["lease_expires_at"] > job["started_at"]
    # Nobody can queue it again while it is running.
    refused = client.post(f"/cases/{case_id}/retry", headers=guest)
    assert refused.status_code == 409 and "being processed" in refused.json()["detail"]

    first.execute(case_id)
    case = detail(client, guest, case_id)
    assert case["status"] == "awaiting_approval"
    assert case["job"]["status"] == "waiting" and case["job"]["worker_id"] == "host:1:a"
    assert case["job"]["lease_expires_at"] is None
    # A worker that did not claim the job cannot finish or fail it either.
    from policy_update import service

    with app.state.sessions.begin() as session:
        with pytest.raises(service.LeaseLost):
            service.finish_job(session, session.get(Case, case_id), "host:2:b", "completed")


def test_stalled_job_is_swept_back_to_the_queue_and_run_by_a_live_worker(app, client, guest, chat):
    chat.decisions += [call("submit_for_approval", changes=EMAIL)]
    case_id = intake(client, guest)
    dead_running_job(app, case_id)
    # Any worker pass recovers it: sweep, re-queue, claim, run.
    assert drain(client) == [case_id]
    case = detail(client, guest, case_id)
    assert case["status"] == "awaiting_approval"
    stalled = events(case, "processing_stalled")
    assert [e["details"] for e in stalled] == [
        {"action": "process", "attempt": 1, "status": "queued"}
    ]
    assert case["job"]["attempts"] == 2
    assert case["job"]["worker_id"] == app.state.worker.id
    assert case["job"]["status"] == "waiting"


def test_job_that_keeps_stalling_fails_for_manual_retry(app, client, guest, chat):
    case_id = intake(client, guest)
    dead_running_job(app, case_id, attempts=app.state.worker.max_attempts)
    assert drain(client) == []
    case = detail(client, guest, case_id)
    assert case["status"] == "received"
    assert case["job"]["status"] == "failed" and case["job"]["retryable"] is True
    limit = app.state.worker.max_attempts
    assert case["job"]["last_error"] == f"Processing stalled {limit} times; retry manually"
    assert events(case, "processing_stalled")[0]["details"]["status"] == "failed"
    chat.decisions += [call("submit_for_approval", changes=EMAIL)]
    case = run(client, guest, case_id, "retry")
    assert case["status"] == "awaiting_approval" and case["job"]["attempts"] == limit + 1


def test_worker_that_lost_its_lease_stops_before_acting_again(app, client, guest, chat):
    """A worker paused past its lease (say, a slow model call) must not keep driving a
    case another worker has taken over. The ownership check inside each step's
    transaction stops it, and the new owner continues from the checkpoint."""

    def take_over():
        set_job(app, case_id, worker_id="host:9:other", lease_expires_at=FAR_FUTURE)
        return call("submit_for_approval", "Never executed by the old owner.", changes=EMAIL)

    chat.decisions += [call("get_policy"), take_over]
    case_id = intake(client, guest)
    queue(client, guest, case_id)
    assert drain(client) == [case_id]
    case = detail(client, guest, case_id)
    assert case["status"] == "processing"
    assert [e["details"]["tool"] for e in events(case, "tool_called")] == ["get_policy"]
    # The old owner neither acted on the second decision nor touched the job.
    assert [e["details"]["step"] for e in events(case, "agent_decision")] == [1]
    assert events(case, "processing_failed") == [] and events(case, "processing_finished") == []
    assert case["job"]["worker_id"] == "host:9:other" and case["job"]["status"] == "running"

    # The new owner dies too; its lapsed lease is swept and the loop continues from
    # the checkpoint after get_policy rather than starting over.
    set_job(app, case_id, lease_expires_at=EXPIRED)
    chat.decisions += [call("submit_for_approval", changes=EMAIL)]
    assert drain(client) == [case_id]
    case = detail(client, guest, case_id)
    assert case["status"] == "awaiting_approval"
    assert [e["details"]["tool"] for e in events(case, "tool_called")] == [
        "get_policy",
        "submit_for_approval",
    ]
    assert chat.prompts[-1]["messages"][-2]["name"] == "get_policy"
    assert case["job"]["attempts"] == 2 and case["job"]["status"] == "waiting"


def test_heartbeat_renews_the_lease_while_a_step_is_slow(app, client, guest, chat):
    worker = Worker(app.state.sessions, None, app.state.agent, "host:1:slow", lease_seconds=1)
    sweeper = Worker(app.state.sessions, None, app.state.agent, "host:2:sweeper")
    seen = {}

    def slow_decision():
        # A model call longer than the lease: the heartbeat (every lease/3) must have
        # renewed it, so a sweeper finds nothing stalled and the job stays ours.
        seen["at_claim"] = detail(client, guest, case_id)["job"]["lease_expires_at"]
        time.sleep(1.5)
        seen["swept"] = sweeper.sweep_stalled()
        seen["renewed"] = detail(client, guest, case_id)["job"]["lease_expires_at"]
        return call("submit_for_approval", changes=EMAIL)

    chat.decisions += [slow_decision]
    case_id = intake(client, guest)
    queue(client, guest, case_id)
    assert worker.run_pending() == [case_id]
    assert seen["swept"] == []
    assert seen["renewed"] > seen["at_claim"]
    case = detail(client, guest, case_id)
    assert case["status"] == "awaiting_approval"
    assert case["job"]["worker_id"] == "host:1:slow" and case["job"]["attempts"] == 1
    assert events(case, "processing_stalled") == []


def test_requeued_attempt_runs_what_the_case_needs_now(app, client, guest, chat):
    # (a) The worker died after committing the whole run but before closing the job:
    # the re-queued attempt finds nothing to run and records the job as waiting.
    chat.decisions += [call("submit_for_approval", changes=EMAIL)]
    case_id = intake(client, guest)
    case = run(client, guest, case_id)
    assert case["status"] == "awaiting_approval"
    set_job(app, case_id, status="running", worker_id="host:1:dead", lease_expires_at=EXPIRED)
    assert drain(client) == [case_id]
    case = detail(client, guest, case_id)
    assert case["job"]["status"] == "waiting" and case["job"]["attempts"] == 2
    assert case["current_version"] == 1 and events(case, "processing_failed") == []
    assert len(events(case, "processing_finished")) == 2

    # (b) A resume attempt failed at its first decision (the case is still approved):
    # the swept attempt resumes the interrupted loop again rather than starting a
    # new run or failing on "cannot be resumed".
    assert action(client, guest, case, "approve").status_code == 200
    chat.decisions += [ModelError("Model request returned HTTP 503", retryable=True)]
    case = run(client, guest, case_id, "resume")
    assert case["status"] == "approved" and case["job"]["status"] == "failed"
    assert case["job"]["action"] == "resume"
    set_job(app, case_id, status="running", worker_id="host:1:dead", lease_expires_at=EXPIRED)
    chat.decisions += [call("apply_approved_update", version=1)]
    assert drain(client) == [case_id]
    case = detail(client, guest, case_id)
    assert case["status"] == "completed" and case["job"]["status"] == "completed"
    assert case["job"]["attempts"] == 4


def test_embedded_worker_thread_runs_jobs_outside_the_request(tmp_path, chat):
    chat.decisions += [
        call("submit_for_approval", changes=EMAIL),
        call("apply_approved_update", version=1),
    ]
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'embedded.db'}")
    app = create_app(url, model=None, agent_model=chat, worker_mode="embedded")
    with TestClient(app) as client:
        assert client.get("/health").json()["worker"] == "embedded"
        guest = {"Authorization": f"Bearer {client.post('/workspaces').json()['token']}"}
        case_id = intake(client, guest)
        queued = queue(client, guest, case_id)
        assert queued["status"] == "received" and queued["job"]["status"] == "queued"
        case = wait_for_job(client, guest, case_id)
        assert case["status"] == "awaiting_approval"
        assert case["job"]["worker_id"] == app.state.worker.id
        assert action(client, guest, case, "approve").status_code == 200
        queue(client, guest, case_id, "resume")
        case = wait_for_job(client, guest, case_id)
        assert case["status"] == "completed" and case["job"]["status"] == "completed"
        assert app.state.worker._thread is not None
    # Shutdown joined the thread.
    assert app.state.worker._thread is None


def test_separate_worker_process_runs_queued_jobs(tmp_path):
    """The real deployment shape: the API only queues; ``python -m policy_update.worker``
    over the same database claims and runs the job (rule-based here: no key)."""
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'external.db'}")
    root = Path(__file__).resolve().parent.parent
    env = {
        **os.environ,
        "PYTHONPATH": str(root / "src"),
        "DATABASE_URL": url,
        "WORKER_POLL_SECONDS": "0.1",
    }
    env.pop("GEMINI_API_KEY", None)
    process = subprocess.Popen(
        [sys.executable, "-m", "policy_update.worker"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        with TestClient(create_app(url, model=None)) as client:
            assert client.get("/health").json()["worker"] == "external"
            guest = {"Authorization": f"Bearer {client.post('/workspaces').json()['token']}"}
            case_id = intake(client, guest, changes=EMAIL)
            queue(client, guest, case_id)
            case = wait_for_job(client, guest, case_id, timeout=30)
            assert case["status"] == "awaiting_approval"
            assert case["job"]["status"] == "waiting"
            assert case["job"]["worker_id"] != client.app.state.worker.id
            assert str(process.pid) in case["job"]["worker_id"]
    finally:
        process.terminate()
        output, _ = process.communicate(timeout=15)
    assert process.returncode == 0, output
    assert "polling every 0.1s" in output
    # Never the request text, the token, or a key.
    assert REQUEST not in output and guest["Authorization"][7:] not in output


def test_bootstrap_adds_columns_missing_from_an_older_database(app, client):
    engine = app.state.engine
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE processing_jobs DROP COLUMN lease_expires_at"))
    initialize_database(engine)
    with engine.begin() as connection:
        connection.execute(text("SELECT lease_expires_at FROM processing_jobs WHERE 1 = 0")).all()
    # Idempotent: a second bootstrap over the complete schema changes nothing.
    initialize_database(engine)
