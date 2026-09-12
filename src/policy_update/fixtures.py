"""Fictional, server-owned fixtures and sample documents.

Evidence dictionaries are not documents. The sample documents are synthetic PDF/PNG
files a guest can download and upload as attachments to exercise real inspection.
"""

from importlib import resources

BROKERS = [
    {"id": "broker-alex", "name": "Alex Morgan", "policy_numbers": ["DEMO-1001"]},
    {"id": "broker-jordan", "name": "Jordan Ellis", "policy_numbers": ["DEMO-2002"]},
]

EVIDENCE = {
    "matching-address": {
        "name": "Sam Taylor",
        "address": "42 Orchard Lane, Demo City, 10001",
        "readable": True,
        "certain": True,
    },
    "conflicting-address": {
        "name": "Sam Taylor",
        "address": "99 River Road, Demo City, 10001",
        "readable": True,
        "certain": True,
    },
    "wrong-name": {
        "name": "Casey Parker",
        "address": "42 Orchard Lane, Demo City, 10001",
        "readable": True,
        "certain": True,
    },
    "unreadable": {"name": "", "address": "", "readable": False, "certain": False},
}

SAMPLES = [
    {
        "title": "Contact-only update",
        "intake": {
            "broker_id": "broker-alex",
            "policy_number": "DEMO-1001",
            "original_request": "For policy DEMO-1001, update Sam Taylor's email to "
            "sam.updated@example.com and phone to +1 202 555 0148.",
            "changes": {"email": "sam.updated@example.com", "phone": "+1 202 555 0148"},
        },
    },
    {
        "title": "Valid address update (fixture evidence)",
        "intake": {
            "broker_id": "broker-alex",
            "policy_number": "DEMO-1001",
            "original_request": "For DEMO-1001, please update Sam Taylor's mailing address "
            "to 42 Orchard Lane, Demo City, 10001. Fictional address evidence attached.",
            "changes": {"mailing_address": "42 Orchard Lane, Demo City, 10001"},
            "evidence_id": "matching-address",
        },
    },
    {
        "title": "Missing evidence (all changes pause)",
        "intake": {
            "broker_id": "broker-alex",
            "policy_number": "DEMO-1001",
            "original_request": "For DEMO-1001, please update the mailing address to "
            "42 Orchard Lane, Demo City, 10001 and email to sam.updated@example.com.",
            "changes": {
                "mailing_address": "42 Orchard Lane, Demo City, 10001",
                "email": "sam.updated@example.com",
            },
        },
    },
    {
        "title": "Conflicting evidence",
        "intake": {
            "broker_id": "broker-alex",
            "policy_number": "DEMO-1001",
            "original_request": "For DEMO-1001, please update the mailing address to "
            "42 Orchard Lane, Demo City, 10001. Fictional evidence attached.",
            "changes": {"mailing_address": "42 Orchard Lane, Demo City, 10001"},
            "evidence_id": "conflicting-address",
        },
    },
    # Free-text intakes carry no ``changes``; processing extracts them with the hosted
    # model when one is configured (GEMINI_API_KEY), otherwise they pause for review.
    {
        "title": "Free-text contact update (model extraction)",
        "intake": {
            "broker_id": "broker-alex",
            "original_request": "Hi, this is Alex Morgan. Policy DEMO-1001: Sam Taylor has a "
            "new phone number, +1 202 555 0177, and a new email, sam.taylor@example.net. "
            "Thanks!",
        },
    },
    {
        "title": "Free-text request with an unsupported change (pauses for review)",
        "intake": {
            "broker_id": "broker-alex",
            "original_request": "Please update the email for Sam Taylor on policy DEMO-1001 "
            "to sam.new@example.com and also increase the liability coverage to $2M.",
        },
    },
]


DOCUMENTS = {
    "matching-pdf": {
        "filename": "proof-matching.pdf",
        "content_type": "application/pdf",
        "title": "Matching proof of address (fields on page 2)",
        "expected": "certain; matches Sam Taylor at 42 Orchard Lane, Demo City, 10001",
    },
    "conflicting-pdf": {
        "filename": "proof-conflicting-address.pdf",
        "content_type": "application/pdf",
        "title": "Conflicting address",
        "expected": "certain; address_conflict for 42 Orchard Lane",
    },
    "wrong-name-pdf": {
        "filename": "proof-wrong-name.pdf",
        "content_type": "application/pdf",
        "title": "Wrong account holder",
        "expected": "certain; name_conflict for Sam Taylor",
    },
    "scanned-pdf": {
        "filename": "proof-scanned.pdf",
        "content_type": "application/pdf",
        "title": "Scan without a text layer",
        "expected": "unreadable; uncertain_evidence",
    },
    "missing-fields-pdf": {
        "filename": "proof-missing-fields.pdf",
        "content_type": "application/pdf",
        "title": "Readable statement without labeled fields",
        "expected": "readable but uncertain; uncertain_evidence",
    },
    "injection-pdf": {
        "filename": "proof-injection.pdf",
        "content_type": "application/pdf",
        "title": "Matching proof containing embedded instructions",
        "expected": "certain; instruction text is ignored and approval is still required",
    },
    "matching-png": {
        "filename": "proof-matching.png",
        "content_type": "image/png",
        "title": "Matching proof as an image",
        "expected": "stored but uncertain until the model adapter (A01) can inspect images",
    },
}


def document_bytes(document_id: str) -> bytes:
    path = resources.files("policy_update").joinpath("assets", DOCUMENTS[document_id]["filename"])
    return path.read_bytes()


def evidence_snapshot(evidence_id: str):
    return {
        **EVIDENCE[evidence_id],
        "source": {"kind": "synthetic_fixture", "id": evidence_id, "page": 1},
    }
