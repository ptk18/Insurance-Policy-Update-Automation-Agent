"""Fictional, server-owned fixtures. These are not uploaded or authenticated documents."""

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
]


def evidence_snapshot(evidence_id: str | None):
    if evidence_id is None:
        return None
    return {
        **EVIDENCE[evidence_id],
        "source": {"kind": "synthetic_fixture", "id": evidence_id, "page": 1},
    }
