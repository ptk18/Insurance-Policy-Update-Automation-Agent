"""Bounded LangGraph loop (A03–A05) with a scripted model: genuine tool selection,
interrupts for approval and information, budget, forbidden tools, crash continuation,
restart, and isolation. No live model is ever called."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from helpers import FakeChat, FakeModel, action, answer, call, stop
from policy_update.api import create_app
from policy_update.extraction import ModelError

REQUEST = "For DEMO-1001 please move Sam Taylor to 42 Orchard Lane, Demo City, 10001."
ADDRESS = {"mailing_address": "42 Orchard Lane, Demo City, 10001"}


@pytest.fixture
def chat():
    return FakeChat()


@pytest.fixture
def app(tmp_path, chat):
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
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


def process(client, guest, case_id, expected=200):
    response = client.post(f"/cases/{case_id}/process", headers=guest)
    assert response.status_code == expected, response.text
    return response.json()


def resume(client, guest, case_id, expected=200):
    response = client.post(f"/cases/{case_id}/resume", headers=guest)
    assert response.status_code == expected, response.text
    return response.json()


def events(case, name):
    return [event for event in case["timeline"] if event["action"] == name]


def codes(case):
    return [finding["code"] for finding in case["proposals"][-1]["findings"]]


def test_agent_selects_tools_waits_for_human_approval_and_applies(client, guest, chat):
    assert client.get("/health").json()["agent"] == "fake:chat"
    chat.decisions += [
        call("get_policy", "Look up the policy."),
        call("inspect_document", "Inspect the proof.", evidence_id="matching-address"),
        call("validate_proposed_changes", changes=ADDRESS),
        call("submit_for_approval", "Submit for approval.", changes=ADDRESS),
    ]
    case_id = intake(client, guest)
    case = process(client, guest, case_id)
    assert case["status"] == "awaiting_approval"
    assert case["current_version"] == 1
    assert case["proposals"][0]["changes"] == ADDRESS
    assert chat.decisions == []

    # What the model saw: the goal, the eight tools, the request marked as data, and
    # no policy values until get_policy returned them.
    first = chat.prompts[0]
    assert "human approval" in first["system"]
    assert [tool["name"] for tool in first["tools"]] == [
        "get_policy",
        "check_broker_assignment",
        "inspect_document",
        "validate_proposed_changes",
        "draft_follow_up",
        "submit_for_approval",
        "apply_approved_update",
        "draft_confirmation",
    ]
    assert all("$ref" not in json.dumps(tool) for tool in first["tools"])
    snapshot = json.loads(first["messages"][-1]["text"].split("(JSON): ", 1)[1])
    assert snapshot["request_text_data"] == REQUEST
    assert snapshot["status"] == "processing" and snapshot["latest_proposal"] is None
    assert "Meadow" not in json.dumps(first["messages"])
    second = chat.prompts[1]["messages"]
    assert second[-2]["role"] == "tool" and second[-2]["response"]["result"]["holder_name"] == (
        "Sam Taylor"
    )

    assert [e["details"]["tool"] for e in events(case, "tool_called")] == [
        "get_policy",
        "inspect_document",
        "validate_proposed_changes",
        "submit_for_approval",
    ]
    decisions = events(case, "agent_decision")
    assert [d["details"]["summary"] for d in decisions][:2] == [
        "Look up the policy.",
        "Inspect the proof.",
    ]
    assert events(case, "processing_started")[0]["details"] == {"mode": "agent"}
    assert events(case, "proposal_validated")[0]["details"]["source"] == "agent_tool"

    # Approval is a human action; resuming before it is refused.
    assert resume(client, guest, case_id, expected=409)["detail"].startswith("Approve or reject")
    assert action(client, guest, case, "approve").status_code == 200
    chat.decisions += [call("apply_approved_update", "Apply the approved version.", version=1)]
    case = resume(client, guest, case_id)
    assert case["status"] == "completed"
    assert case["confirmation_draft"].startswith("Draft only")
    assert chat.decisions == []
    resumed = chat.prompts[-1]["messages"]
    assert any("resumed this case after: approval" in m.get("text", "") for m in resumed)
    finished = events(case, "agent_finished")
    assert finished[-1]["details"]["status"] == "completed"
    assert action(client, guest, case, "execute").json()["proposal_version"] == 1
    assert process(client, guest, case_id, expected=409)
    assert resume(client, guest, case_id, expected=409)


def test_agent_asks_for_information_and_continues_after_a_reply(client, guest, chat):
    chat.decisions += [
        call("draft_follow_up", "Ask for the policy number.", questions=["Which policy?"]),
    ]
    case_id = intake(client, guest, policy_number=None, original_request="Sam moved.")
    case = process(client, guest, case_id)
    assert case["status"] == "awaiting_information"
    assert "Which policy?" in case["follow_up_draft"]
    assert codes(case) == ["clarification_requested", "missing_policy"]

    reply = client.post(
        f"/cases/{case_id}/replies",
        headers=guest,
        json={
            "expected_version": 1,
            "text": "Policy DEMO-1001, email sam.updated@example.com.",
            "policy_number": "DEMO-1001",
        },
    )
    assert reply.status_code == 200 and reply.json()["current_version"] == 2
    chat.decisions += [
        call("get_policy"),
        call("submit_for_approval", changes={"email": "sam.updated@example.com"}),
    ]
    case = resume(client, guest, case_id)
    assert case["status"] == "awaiting_approval"
    assert case["current_version"] == 3
    snapshot = json.loads(chat.prompts[-2]["messages"][-1]["text"].split("(JSON): ", 1)[1])
    assert snapshot["replies_data"] == ["Policy DEMO-1001, email sam.updated@example.com."]
    assert snapshot["latest_proposal"]["version"] == 2


def test_model_that_stops_without_acting_pauses_for_a_human(client, guest, chat):
    chat.decisions += [call("check_broker_assignment"), stop("Nothing more I can do here.")]
    case_id = intake(client, guest)
    case = process(client, guest, case_id)
    assert case["status"] == "awaiting_information"
    assert codes(case) == ["agent_stopped", "missing_changes"]
    assert "Nothing more I can do here." in case["follow_up_draft"]
    assert events(case, "agent_finished")[0]["details"]["outcome"] == (
        "Nothing more I can do here."
    )
    assert events(case, "proposal_validated")[0]["details"]["source"] == "agent_loop"


def test_tool_budget_stops_the_loop_for_review(tmp_path, monkeypatch, chat):
    monkeypatch.setenv("AGENT_TOOL_BUDGET", "2")
    chat.decisions += [call("check_broker_assignment")] * 3
    app = create_app(f"sqlite:///{tmp_path / 'budget.db'}", model=None, agent_model=chat)
    with TestClient(app) as client:
        guest = {"Authorization": f"Bearer {client.post('/workspaces').json()['token']}"}
        case_id = intake(client, guest)
        case = process(client, guest, case_id)
    assert case["status"] == "awaiting_information"
    assert codes(case)[0] == "agent_stopped"
    assert "tool-call limit" in case["follow_up_draft"]
    assert len(events(case, "tool_called")) == 2
    assert len(chat.decisions) == 1


def test_forbidden_or_unknown_tool_calls_are_observed_not_executed(client, guest, chat):
    chat.decisions += [
        call("approve_proposal", version=1),
        call("get_policy", policy_number="DEMO-2002"),
        stop("Cannot proceed."),
    ]
    case_id = intake(client, guest)
    case = process(client, guest, case_id)
    assert case["status"] == "awaiting_information"
    outcomes = [e["details"]["outcome"] for e in events(case, "tool_called")]
    assert outcomes == ["unknown_tool", "policy_mismatch"]
    observed = chat.prompts[1]["messages"][-2]["response"]
    assert observed == {
        "ok": False,
        "error": "unknown_tool",
        "message": "No tool named approve_proposal",
    }
    assert case["proposals"][0]["status"] == "invalid"
    assert action(client, guest, case, "execute").status_code == 409


def test_model_failure_keeps_the_case_processing_and_continues_from_checkpoint(client, guest, chat):
    chat.decisions += [
        call("get_policy"),
        ModelError("Model request returned HTTP 503", retryable=True),
    ]
    case_id = intake(client, guest)
    failed = process(client, guest, case_id, expected=503)
    assert "retried" in failed["detail"]
    case = client.get(f"/cases/{case_id}", headers=guest).json()
    assert case["status"] == "processing"
    assert len(events(case, "tool_called")) == 1
    assert case["job"]["status"] == "failed" and case["job"]["retryable"] is True
    assert case["job"]["last_error"] == "The hosted model is unavailable; processing can be retried"
    assert events(case, "processing_failed")[0]["details"]["attempt"] == 1
    assert client.get("/cases", headers=guest).json()[0]["job_status"] == "failed"
    # A resume makes no sense here; the API points at the right recovery action.
    assert (
        resume(client, guest, case_id, expected=409)["detail"] == "Use /retry to continue this case"
    )

    chat.decisions += [call("submit_for_approval", changes={"email": "sam.new@example.com"})]
    case = client.post(f"/cases/{case_id}/retry", headers=guest).json()
    assert case["status"] == "awaiting_approval"
    assert case["job"] == {
        **{key: case["job"][key] for key in ("started_at", "updated_at")},
        "action": "continue",
        "status": "waiting",
        "attempts": 2,
        "retryable": False,
        "last_error": None,
    }
    # The first step was not repeated: the loop continued from its checkpoint.
    assert [e["details"]["tool"] for e in events(case, "tool_called")] == [
        "get_policy",
        "submit_for_approval",
    ]
    assert chat.prompts[-1]["messages"][-2]["name"] == "get_policy"


def test_interrupted_loop_survives_an_app_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'restart.db'}"
    first_chat = FakeChat(call("submit_for_approval", changes={"email": "sam.new@example.com"}))
    with TestClient(create_app(url, model=None, agent_model=first_chat)) as first:
        token = first.post("/workspaces").json()["token"]
        guest = {"Authorization": f"Bearer {token}"}
        case_id = intake(first, guest)
        case = process(first, guest, case_id)
        assert case["status"] == "awaiting_approval"
        assert action(first, guest, case, "approve").status_code == 200

    second_chat = FakeChat(call("apply_approved_update", version=1))
    with TestClient(create_app(url, model=None, agent_model=second_chat)) as second:
        case = resume(second, guest, case_id)
        assert case["status"] == "completed"
        assert second_chat.decisions == []
        assert second_chat.prompts[0]["messages"][-3]["name"] == "submit_for_approval"


def test_other_guests_cannot_process_or_resume_the_case(client, guest, chat):
    chat.decisions += [call("submit_for_approval", changes={"email": "sam.new@example.com"})]
    case_id = intake(client, guest)
    other = {"Authorization": f"Bearer {client.post('/workspaces').json()['token']}"}
    assert client.post(f"/cases/{case_id}/process", headers=other).status_code == 404
    assert client.post(f"/cases/{case_id}/process").status_code == 401
    case = process(client, guest, case_id)
    assert action(client, guest, case, "approve").status_code == 200
    assert client.post(f"/cases/{case_id}/resume", headers=other).status_code == 404


def test_extraction_feeds_the_loop_without_creating_a_proposal(tmp_path, chat):
    extractor = FakeModel(
        answer(
            policy_number="DEMO-1001",
            email="sam.taylor@example.net",
            unsupported_requests=["increase coverage"],
        )
    )
    # The model submits only the permitted part; the backend still pauses on the rest.
    chat.decisions += [call("submit_for_approval", changes={"email": "sam.taylor@example.net"})]
    app = create_app(f"sqlite:///{tmp_path / 'extract.db'}", model=extractor, agent_model=chat)
    with TestClient(app) as client:
        guest = {"Authorization": f"Bearer {client.post('/workspaces').json()['token']}"}
        case_id = intake(
            client,
            guest,
            policy_number=None,
            original_request="Policy DEMO-1001: email sam.taylor@example.net, increase coverage.",
        )
        case = process(client, guest, case_id)
    assert case["policy_number"] == "DEMO-1001"
    assert case["requested_changes"] == {"email": "sam.taylor@example.net"}
    assert case["current_version"] == 1 and case["status"] == "awaiting_information"
    assert codes(case) == ["unsupported_request"]
    assert "increase coverage" in case["follow_up_draft"]
    snapshot = json.loads(chat.prompts[0]["messages"][-1]["text"].split("(JSON): ", 1)[1])
    assert snapshot["extraction_notes"]["unsupported"] == ["increase coverage"]
    assert snapshot["requested_changes"] == {"email": "sam.taylor@example.net"}
    assert [e["action"] for e in case["timeline"]][:3] == [
        "case_created",
        "request_extracted",
        "processing_started",
    ]


def test_stalled_running_job_is_refused_until_retried(app, client, guest, chat):
    from policy_update.models import Case, ProcessingJob

    chat.decisions += [call("submit_for_approval", changes={"email": "sam.new@example.com"})]
    case_id = intake(client, guest)
    # Simulate a process that died mid-run: the job row still says running.
    with app.state.sessions.begin() as session:
        workspace_id = session.get(Case, case_id).workspace_id
        session.add(
            ProcessingJob(
                case_id=case_id,
                workspace_id=workspace_id,
                action="process",
                status="running",
                attempts=1,
            )
        )
    refused = client.post(f"/cases/{case_id}/process", headers=guest)
    assert refused.status_code == 409 and "retry" in refused.json()["detail"]
    case = client.post(f"/cases/{case_id}/retry", headers=guest).json()
    assert case["status"] == "awaiting_approval"
    assert case["job"]["attempts"] == 2 and case["job"]["status"] == "waiting"
    assert action(client, guest, case, "approve").status_code == 200
    chat.decisions += [call("apply_approved_update", version=1)]
    case = client.post(f"/cases/{case_id}/retry", headers=guest).json()
    assert case["status"] == "completed" and case["job"]["status"] == "completed"
    assert case["job"]["action"] == "resume"
