import os

import pytest
from fastapi.testclient import TestClient

from policy_update.api import create_app


@pytest.fixture(autouse=True)
def no_live_model(tmp_path, monkeypatch):
    # Belt and braces: even a create_app() call that forgets model=None must not
    # find a key. The .env loader is pointed at a file that does not exist.
    monkeypatch.setenv("POLICY_UPDATE_ENV_FILE", str(tmp_path / "absent.env"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_LOOP", raising=False)
    # No background worker thread: tests drive app.state.worker deterministically
    # (helpers.run / helpers.drain). A test of the embedded thread opts in explicitly.
    monkeypatch.setenv("WORKER_MODE", "external")


@pytest.fixture
def app(tmp_path):
    # Every test gets fresh guests. No database cleanup or shared-data deletion is needed.
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    # model=None: never load .env or call a hosted model from the suite. Extraction
    # tests build their own app around a scripted FakeModel.
    return create_app(url, model=None)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def guest(client):
    response = client.post("/workspaces")
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def contact():
    return {
        "broker_id": "broker-alex",
        "policy_number": "DEMO-1001",
        "original_request": "For DEMO-1001 update Sam's email to sam.updated@example.com.",
        "changes": {"email": "sam.updated@example.com"},
    }


@pytest.fixture
def address(contact):
    return {
        **contact,
        "changes": {
            "email": "sam.updated@example.com",
            "mailing_address": "42 Orchard Lane, Demo City, 10001",
        },
    }
