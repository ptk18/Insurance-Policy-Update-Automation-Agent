"""Uploaded-document evidence: storage, inspection, validation, isolation (E02–E06)."""

import pytest
from fastapi.testclient import TestClient

from helpers import action, policy, submit
from policy_update.api import create_app


def sample(client, guest, document_id):
    response = client.get(f"/fixtures/documents/{document_id}", headers=guest)
    assert response.status_code == 200, response.text
    return response.content


def upload(client, guest, case_id, content, filename="proof.pdf", declared="application/pdf"):
    return client.post(
        f"/cases/{case_id}/attachments",
        headers=guest,
        files={"file": (filename, content, declared)},
    )


def reply_with(client, guest, case, evidence_id, version):
    return client.post(
        f"/cases/{case['id']}/replies",
        headers=guest,
        json={
            "expected_version": version,
            "text": "Corrected document",
            "evidence_id": evidence_id,
        },
    )


def intake(client, guest, payload):
    response = client.post("/cases", headers=guest, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_fixture_documents_are_listed_and_downloadable(client, guest):
    documents = client.get("/fixtures", headers=guest).json()["documents"]
    assert {doc["id"] for doc in documents} >= {"matching-pdf", "scanned-pdf", "matching-png"}
    for doc in documents:
        response = client.get(doc["download"], headers=guest)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(doc["content_type"])
        assert len(response.content) == doc["size"]
    assert client.get("/fixtures/documents/matching-pdf").status_code == 401
    assert client.get("/fixtures/documents/nope", headers=guest).status_code == 404


def test_uploaded_pdf_is_inspected_with_page_reference_and_supports_execution(
    client, guest, address
):
    case = intake(client, guest, address)
    pdf = sample(client, guest, "matching-pdf")
    uploaded = upload(client, guest, case["id"], pdf, filename="../My Bill (Aug).PDF")
    assert uploaded.status_code == 201, uploaded.text
    attachment = uploaded.json()
    assert attachment["filename"] == "My_Bill__Aug_.PDF"
    assert attachment["content_type"] == "application/pdf"
    assert attachment["size"] == len(pdf)
    assert "content" not in attachment
    inspection = attachment["inspection"]
    assert inspection["name"] == "Sam Taylor"
    assert inspection["address"] == "42 Orchard Lane, Demo City, 10001"
    assert inspection["readable"] and inspection["certain"]
    assert inspection["source"] == {
        "kind": "attachment",
        "id": attachment["id"],
        "filename": "My_Bill__Aug_.PDF",
        "content_type": "application/pdf",
        "page": 2,
        "pages": 2,
    }
    detail = client.get(f"/cases/{case['id']}", headers=guest).json()
    assert detail["evidence_id"] == attachment["id"]
    assert [item["id"] for item in detail["attachments"]] == [attachment["id"]]
    uploaded_event = [e for e in detail["timeline"] if e["action"] == "attachment_uploaded"][0]
    assert uploaded_event["details"]["bound_as_evidence"] is True
    assert "Sam Taylor" not in str(uploaded_event["details"])

    content = client.get(
        f"/cases/{case['id']}/attachments/{attachment['id']}/content", headers=guest
    )
    assert content.status_code == 200
    assert content.content == pdf
    assert content.headers["content-type"] == "application/pdf"
    assert content.headers["cache-control"] == "private, no-store"
    meta = client.get(f"/cases/{case['id']}/attachments/{attachment['id']}", headers=guest)
    assert meta.json()["sha256"] == attachment["sha256"]

    processed = client.post(f"/cases/{case['id']}/process", headers=guest).json()
    assert processed["status"] == "awaiting_approval"
    assert processed["proposals"][0]["evidence"]["source"]["page"] == 2
    assert action(client, guest, case, "approve").status_code == 200
    assert action(client, guest, case, "execute").status_code == 200
    assert policy(client, guest)["mailing_address"] == address["changes"]["mailing_address"]


@pytest.mark.parametrize(
    ("document_id", "finding", "readable"),
    [
        ("conflicting-pdf", "address_conflict", True),
        ("wrong-name-pdf", "name_conflict", True),
        ("scanned-pdf", "uncertain_evidence", False),
        ("missing-fields-pdf", "uncertain_evidence", True),
        ("matching-png", "uncertain_evidence", False),
    ],
)
def test_unresolved_document_blocks_and_corrected_upload_resumes(
    client, guest, address, document_id, finding, readable
):
    case = intake(client, guest, address)
    first = upload(client, guest, case["id"], sample(client, guest, document_id)).json()
    assert first["inspection"]["readable"] is readable
    processed = client.post(f"/cases/{case['id']}/process", headers=guest).json()
    assert processed["status"] == "awaiting_information"
    findings = {item["code"]: item["message"] for item in processed["proposals"][0]["findings"]}
    assert finding in findings
    if not first["inspection"]["certain"]:
        assert first["inspection"]["reasons"]
        assert first["inspection"]["reasons"][0] in findings["uncertain_evidence"]
    assert action(client, guest, case, "approve").status_code == 409

    # A later upload is stored but does not change the case until a reply binds it.
    corrected = upload(client, guest, case["id"], sample(client, guest, "matching-pdf")).json()
    unchanged = client.get(f"/cases/{case['id']}", headers=guest).json()
    assert unchanged["evidence_id"] == first["id"]
    assert unchanged["current_version"] == 1
    assert action(client, guest, case, "approve").status_code == 409

    resumed = reply_with(client, guest, case, corrected["id"], 1)
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body["status"] == "awaiting_approval"
    assert body["current_version"] == 2
    assert body["proposals"][0]["status"] == "superseded"
    assert body["proposals"][0]["evidence"]["source"]["id"] == first["id"]
    assert body["proposals"][1]["evidence"]["source"]["id"] == corrected["id"]
    assert [item["id"] for item in body["attachments"]] == [first["id"], corrected["id"]]
    assert action(client, guest, case, "approve", 2).status_code == 200
    assert action(client, guest, case, "execute", 2).status_code == 200


def test_embedded_document_instructions_only_yield_labeled_fields(client, guest, address):
    case = intake(client, guest, address)
    attachment = upload(client, guest, case["id"], sample(client, guest, "injection-pdf")).json()
    assert attachment["inspection"]["certain"]
    assert "SYSTEM" not in str(attachment["inspection"])
    processed = client.post(f"/cases/{case['id']}/process", headers=guest).json()
    assert processed["status"] == "awaiting_approval"
    assert action(client, guest, case, "execute").status_code == 409
    assert (
        client.get("/policies/DEMO-1001?broker_id=broker-jordan", headers=guest).status_code == 403
    )


def test_upload_validation_rejects_wrong_type_size_and_state(tmp_path, address, contact):
    with TestClient(
        create_app(f"sqlite:///{tmp_path / 'limit.db'}", max_attachment_bytes=1500, model=None)
    ) as c:
        guest = {"Authorization": f"Bearer {c.post('/workspaces').json()['token']}"}
        case = intake(c, guest, address)
        assert (
            upload(c, guest, case["id"], b"just text", declared="application/pdf").status_code
            == 415
        )
        spoofed = b"\x89PNG\r\n\x1a\n" + b"not really an image"
        assert upload(c, guest, case["id"], spoofed, "x.pdf").status_code == 201
        assert upload(c, guest, case["id"], spoofed, "x.pdf").json()["content_type"] == "image/png"
        assert upload(c, guest, case["id"], b"", "empty.pdf").status_code == 422
        assert upload(c, guest, case["id"], b"%PDF-" + b"x" * 1600).status_code == 413
        small = sample(c, guest, "conflicting-pdf")
        assert len(small) < 1500
        assert upload(c, guest, case["id"], small).status_code == 201
        assert upload(c, guest, case["id"], b"%PDF-1.4 broken").json()["inspection"]["reasons"]
        assert upload(c, guest, "missing-case", small).status_code == 404
        detail = c.get(f"/cases/{case['id']}", headers=guest).json()
        assert len(detail["attachments"]) == 4
        assert detail["status"] == "received"

        done = submit(c, guest, contact)
        assert action(c, guest, done, "approve").status_code == 200
        assert action(c, guest, done, "execute").status_code == 200
        assert upload(c, guest, done["id"], small).status_code == 409


def test_attachments_are_isolated_by_workspace_and_case(client, guest, address):
    case = intake(client, guest, address)
    attachment = upload(client, guest, case["id"], sample(client, guest, "matching-pdf")).json()
    other = {"Authorization": f"Bearer {client.post('/workspaces').json()['token']}"}
    base = f"/cases/{case['id']}/attachments/{attachment['id']}"
    assert client.get(base, headers=other).status_code == 404
    assert client.get(base + "/content", headers=other).status_code == 404
    assert client.get(base + "/content").status_code == 401
    assert upload(client, other, case["id"], b"%PDF-1.4").status_code == 404

    # Another guest's own case cannot reference this attachment as evidence.
    foreign = submit(client, other, address)
    assert foreign["status"] == "awaiting_information"
    assert reply_with(client, other, foreign, attachment["id"], 1).status_code == 404
    assert client.get(f"/cases/{foreign['id']}", headers=other).json()["current_version"] == 1

    # Neither can a different case in the same workspace.
    sibling = submit(client, guest, address)
    assert reply_with(client, guest, sibling, attachment["id"], 1).status_code == 404
    assert reply_with(client, guest, sibling, "no-such-evidence", 1).status_code == 404
    assert client.get(f"/cases/{sibling['id']}", headers=guest).json()["current_version"] == 1


def test_attachment_and_binding_survive_restart(tmp_path, address):
    url = f"sqlite:///{tmp_path / 'restart.db'}"
    with TestClient(create_app(url, model=None)) as first:
        guest = {"Authorization": f"Bearer {first.post('/workspaces').json()['token']}"}
        case = intake(first, guest, address)
        pdf = sample(first, guest, "matching-pdf")
        attachment = upload(first, guest, case["id"], pdf).json()
    with TestClient(create_app(url, model=None)) as second:
        detail = second.get(f"/cases/{case['id']}", headers=guest).json()
        assert detail["evidence_id"] == attachment["id"]
        content = second.get(
            f"/cases/{case['id']}/attachments/{attachment['id']}/content", headers=guest
        )
        assert content.content == pdf
        processed = second.post(f"/cases/{case['id']}/process", headers=guest).json()
        assert processed["status"] == "awaiting_approval"
