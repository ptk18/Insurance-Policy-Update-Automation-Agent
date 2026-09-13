"""Migrations and public-demo controls with real storage and no hosted model."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from helpers import FakeChat, action, call, submit
from policy_update import service
from policy_update.api import create_app
from policy_update.cleanup import expired_workspaces, purge_expired
from policy_update.database import (
    initialize_database,
    make_database,
    migration_config,
    require_current_schema,
    upgrade_database,
)
from policy_update.fixtures import document_bytes
from policy_update.limits import consume
from policy_update.models import (
    Attachment,
    Base,
    Case,
    Execution,
    ProcessingJob,
    ResourceUsage,
    Workspace,
)


@pytest.fixture
def migration_db(tmp_path):
    import os
    from uuid import uuid4

    from sqlalchemy.engine import make_url

    target = os.environ.get("TEST_DATABASE_URL")
    if not target:
        engine, sessions = make_database(f"sqlite:///{tmp_path / 'migration.db'}")
        yield engine, sessions
        engine.dispose()
        return
    # A dedicated schema inside the dedicated test DB; never alter another test's records.
    schema = "migration_" + uuid4().hex
    admin, _ = make_database(target)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(target).update_query_dict({"options": f"-csearch_path={schema}"})
    engine, sessions = make_database(url.render_as_string(hide_password=False))
    try:
        yield engine, sessions
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_migration_retains_receipt_evidence_and_replay(migration_db, contact):
    engine, sessions = migration_db
    # Build a real completed case, then represent the same schema before versioning.
    app = create_app(engine.url.render_as_string(hide_password=False), model=None)
    with TestClient(app) as client:
        workspace = client.post("/workspaces").json()
        owner = workspace["workspace_id"]
        guest = {"Authorization": "Bearer " + workspace["token"]}
        case = submit(client, guest, contact)
        assert action(client, guest, case, "approve").status_code == 200
        receipt = action(client, guest, case, "execute").json()
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE resource_usage"))
        connection.execute(text("DROP TABLE alembic_version"))
        connection.execute(text("ALTER TABLE cases DROP COLUMN requested_changes"))
    upgrade_database(engine)
    upgrade_database(engine)
    require_current_schema(engine)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    with TestClient(
        create_app(engine.url.render_as_string(hide_password=False), model=None)
    ) as client:
        assert action(client, guest, case, "execute").json() == receipt
        assert client.get(f"/cases/{case['id']}", headers=guest).json()["status"] == "completed"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Execution)) == 1
        assert session.get(ResourceUsage, f"cases:{owner}").amount == 1
    engine.dispose()


def test_revision_upgrade_retains_attachment_bytes(migration_db):
    engine, sessions = migration_db
    with engine.begin() as connection:
        command.upgrade(migration_config(connection), "0001")
    # Revision 0001 has no quota table yet; insert synthetic retained records directly.
    with sessions.begin() as session:
        workspace = Workspace(token_hash="synthetic-hash")
        session.add(workspace)
        session.flush()
        case = Case(workspace_id=workspace.id, broker_id="broker-alex", original_request="demo")
        session.add(case)
        session.flush()
        attachment = Attachment(
            workspace_id=workspace.id,
            case_id=case.id,
            filename="demo.pdf",
            content_type="application/pdf",
            size=4,
            sha256="synthetic",
            content=b"demo",
            inspection={},
        )
        session.add(attachment)
        session.flush()
        attachment_id, owner = attachment.id, workspace.id
    upgrade_database(engine)
    with sessions() as session:
        assert session.get(Attachment, attachment_id).content == b"demo"
        assert session.get(ResourceUsage, f"bytes:{owner}").amount == 4
    engine.dispose()


def test_expiry_blocks_api_queue_and_worker_then_cleanup_is_isolated(app, client, guest, contact):
    case = client.post("/cases", headers=guest, json=contact).json()
    with app.state.sessions() as session:
        owner = session.get(Case, case["id"]).workspace_id
    # A job queued before expiry must never call the model after expiry.
    assert client.post(f"/cases/{case['id']}/process", headers=guest).status_code == 202
    other = client.post("/workspaces").json()
    with app.state.sessions.begin() as session:
        workspace = session.get(Workspace, owner)
        workspace.created_at = "2000-01-01T00:00:00+00:00"
    for path in ("/cases", f"/cases/{case['id']}", "/fixtures"):
        assert client.get(path, headers=guest).status_code == 401
    assert client.post(f"/cases/{case['id']}/retry", headers=guest).status_code == 401
    app.state.worker.run_pending()
    with app.state.sessions.begin() as session:
        assert session.get(ProcessingJob, case["id"]).status == "failed"
        assert session.get(Case, case["id"]).current_version == 0
        assert owner in expired_workspaces(session)
        purge_expired(session)
        assert session.get(Workspace, owner) is None
        assert session.get(Workspace, other["workspace_id"]) is not None


def test_case_attachment_and_run_limits_rollback_rejected_requests(
    app,
    client,
    guest,
    contact,
    monkeypatch,
):
    monkeypatch.setenv("MAX_WORKSPACE_CASES", "1")
    monkeypatch.setenv("MAX_WORKSPACE_RUNS", "1")
    monkeypatch.setenv("MAX_CASE_ATTACHMENTS", "1")
    case = client.post("/cases", headers=guest, json=contact).json()
    with app.state.sessions() as session:
        owner = session.get(Case, case["id"]).workspace_id
    assert client.post("/cases", headers=guest, json=contact).status_code == 429
    path = f"/cases/{case['id']}"
    pdf = document_bytes("matching-pdf")
    files = {"file": ("demo.pdf", pdf, "application/pdf")}
    assert client.post(path + "/attachments", headers=guest, files=files).status_code == 201
    assert client.post(path + "/attachments", headers=guest, files=files).status_code == 429
    assert client.post(path + "/process", headers=guest).status_code == 202
    assert client.post(path + "/process", headers=guest).status_code == 409
    with app.state.sessions() as session:
        assert session.get(ResourceUsage, f"runs:{owner}").amount == 1
        assert session.get(ResourceUsage, f"bytes:{owner}").amount == len(pdf)
    app.state.worker.run_pending()


def test_shared_quota_cannot_be_oversubscribed(app, client):
    # Independent database sessions race; exactly one reservation is allowed.
    import uuid

    key = f"race:{uuid.uuid4()}"

    def reserve():
        try:
            with app.state.sessions.begin() as session:
                consume(session, key, 1)
            return True
        except service.DomainError as error:
            assert error.status == 429
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: reserve(), range(2))) == [False, True]


def test_body_limit_before_multipart_parsing(client, guest):
    result = client.post("/cases", headers=guest, content=b"x" * (6 * 1024 * 1024 + 1))
    assert result.status_code == 413
    assert "xxxx" not in result.text


def test_verify_mode_refuses_an_unmigrated_database(tmp_path, monkeypatch):
    engine, _ = make_database(f"sqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setenv("SCHEMA_MODE", "verify")
    with pytest.raises(RuntimeError, match="upgrade required"):
        initialize_database(engine)
    engine.dispose()


def test_cleanup_removes_real_checkpoints_and_evidence(migration_db, contact):
    engine, sessions = migration_db
    chat = FakeChat(call("submit_for_approval", changes=contact["changes"]))
    app = create_app(engine.url.render_as_string(hide_password=False), model=None, agent_model=chat)
    with TestClient(app) as client:
        workspace = client.post("/workspaces").json()
        guest = {"Authorization": "Bearer " + workspace["token"]}
        case = submit(client, guest, contact)
        assert app.state.agent.state(case["id"]).interrupts
        result = client.post(
            f"/cases/{case['id']}/attachments",
            headers=guest,
            files={"file": ("proof.pdf", document_bytes("matching-pdf"), "application/pdf")},
        )
        assert result.status_code == 201
    with sessions.begin() as session:
        session.get(Workspace, workspace["workspace_id"]).created_at = "2000-01-01T00:00:00+00:00"
    with sessions.begin() as session:
        purge_expired(session)
    assert not app.state.agent.state(case["id"]).values
    with sessions() as session:
        assert session.get(Attachment, result.json()["id"]) is None
        assert session.get(Case, case["id"]) is None


def test_global_queue_limit_rolls_back_new_job_and_guest_budget(
    app,
    client,
    guest,
    contact,
    monkeypatch,
):
    from datetime import UTC, datetime

    key = f"daily-runs:{datetime.now(UTC).date().isoformat()}"
    with app.state.sessions.begin() as session:
        existing = session.get(ResourceUsage, key)
        maximum = (existing.amount if existing else 0) + 1
    monkeypatch.setenv("MAX_DAILY_RUNS", str(maximum))
    first = client.post("/cases", headers=guest, json=contact).json()
    second = client.post("/cases", headers=guest, json=contact).json()
    assert client.post(f"/cases/{first['id']}/process", headers=guest).status_code == 202
    assert client.post(f"/cases/{second['id']}/process", headers=guest).status_code == 429
    with app.state.sessions() as session:
        assert session.get(ProcessingJob, second["id"]) is None
        owner = session.get(Case, first["id"]).workspace_id
        assert session.get(ResourceUsage, f"runs:{owner}").amount == 1
    app.state.worker.run_pending()
