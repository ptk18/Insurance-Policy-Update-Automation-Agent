"""Shared API helpers for the backend test modules."""


def submit(client, guest, payload):
    # Intake persists first; processing is a separate request and transaction.
    response = client.post("/cases", headers=guest, json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "received"
    processed = client.post(f"/cases/{response.json()['id']}/process", headers=guest)
    assert processed.status_code == 200, processed.text
    return processed.json()


def action(client, guest, case, name, version=1):
    return client.post(f"/cases/{case['id']}/{name}", headers=guest, json={"version": version})


def policy(client, guest):
    response = client.get("/policies/DEMO-1001?broker_id=broker-alex", headers=guest)
    assert response.status_code == 200
    return response.json()
