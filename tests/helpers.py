"""Shared API helpers for the backend test modules."""


def drain(client):
    """Run the app's worker to completion in this thread (WORKER_MODE=external in
    tests, so nothing runs in the background). Returns the case IDs it processed."""
    return client.app.state.worker.run_pending()


def run(client, guest, case_id, route="process", expected=202):
    """Queue ``route`` (process/resume/retry) for a case, let the worker run it, and
    return the stored case. With ``expected`` != 202 the refusal is returned instead."""
    response = client.post(f"/cases/{case_id}/{route}", headers=guest)
    assert response.status_code == expected, response.text
    if expected != 202:
        return response.json()
    assert response.json()["job"]["status"] == "queued"
    drain(client)
    detail = client.get(f"/cases/{case_id}", headers=guest)
    assert detail.status_code == 200, detail.text
    return detail.json()


def submit(client, guest, payload):
    # Intake persists first; processing is queued by a separate request and run by
    # the worker in its own transactions.
    response = client.post("/cases", headers=guest, json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "received"
    return run(client, guest, response.json()["id"])


def action(client, guest, case, name, version=1):
    return client.post(f"/cases/{case['id']}/{name}", headers=guest, json={"version": version})


def policy(client, guest):
    response = client.get("/policies/DEMO-1001?broker_id=broker-alex", headers=guest)
    assert response.status_code == 200
    return response.json()


class FakeModel:
    """Scripted stand-in for the hosted model: no network, deterministic answers.

    Each queued item is either a raw answer dict (missing schema keys default to
    empty) or an exception to raise. An unexpected call fails loudly."""

    name = "fake:scripted"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.contexts = []

    def extract(self, text, context=None):
        from policy_update.extraction import ModelResponse

        self.calls.append(text)
        self.contexts.append(context)
        if not self.responses:
            raise AssertionError("The model was called but no response was scripted")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return ModelResponse(data=answer(**item), usage={"totalTokenCount": 1})


def answer(**fields):
    return {
        "policy_number": None,
        "mailing_address": None,
        "email": None,
        "phone": None,
        "unsupported_requests": [],
        "ambiguities": [],
        **fields,
    }


def upload_doc(client, guest, case_id, document_id):
    content = client.get(f"/fixtures/documents/{document_id}", headers=guest).content
    response = client.post(
        f"/cases/{case_id}/attachments",
        headers=guest,
        files={"file": (f"{document_id}.pdf", content, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


class FakeChat:
    """Scripted tool-selection model for the agent loop. Queue ``call(...)`` and
    ``stop(...)`` decisions or exceptions; every prompt it saw is kept for assertions."""

    name = "fake:chat"

    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.prompts = []

    def choose(self, system, messages, tools):
        self.prompts.append({"system": system, "messages": messages, "tools": tools})
        if not self.decisions:
            raise AssertionError("The agent model was asked to decide but nothing was scripted")
        item = self.decisions.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            # A hook: lets a test change the world (for example take over the job's
            # lease) between two decisions, then returns the decision to use.
            return item()
        return item


def call(name, summary="", **arguments):
    from policy_update.extraction import Decision

    return Decision(name, arguments, summary or f"Calling {name}.")


def stop(summary):
    from policy_update.extraction import Decision

    return Decision(None, {}, summary)
