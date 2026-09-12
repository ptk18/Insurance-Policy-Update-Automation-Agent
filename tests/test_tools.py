"""Typed agent tools (A02): scoping, authorization, grounding, versioning, budget, and
the absence of reviewer operations. Tools run in a service session; approval goes
through the API because the tools must not be able to do it."""

import contextlib
import json

import pytest

from helpers import action, submit, upload_doc
from policy_update.models import Case
from policy_update.tools import (
    DEFAULT_TOOL_BUDGET,
    TOOLS,
    BudgetExhausted,
    ToolContext,
    run_tool,
    tool_schemas,
)

EXPECTED_TOOLS = [
    "get_policy",
    "check_broker_assignment",
    "inspect_document",
    "validate_proposed_changes",
    "draft_follow_up",
    "submit_for_approval",
    "apply_approved_update",
    "draft_confirmation",
]


@pytest.fixture
def agent(app):
    """Run one tool call in its own transaction, like one worker step."""

    @contextlib.contextmanager
    def step(case_id, budget=DEFAULT_TOOL_BUDGET):
        with app.state.sessions.begin() as session:
            case = session.get(Case, case_id)
            yield ToolContext(session, case, budget=budget)

    def call(case_id, name, arguments=None, **kwargs):
        with step(case_id, **kwargs) as context:
            return run_tool(context, name, arguments)

    call.step = step
    return call


def received(client, guest, **overrides):
    payload = {
        "broker_id": "broker-alex",
        "policy_number": "DEMO-1001",
        "original_request": "For DEMO-1001 update Sam's email to sam.updated@example.com.",
        **overrides,
    }
    response = client.post("/cases", headers=guest, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def timeline(client, guest, case_id, name):
    case = client.get(f"/cases/{case_id}", headers=guest).json()
    return [event for event in case["timeline"] if event["action"] == name]


def test_registry_exposes_exactly_the_eight_permitted_tools():
    assert list(TOOLS) == EXPECTED_TOOLS
    schemas = tool_schemas()
    assert [schema["name"] for schema in schemas] == EXPECTED_TOOLS
    for schema in schemas:
        assert schema["parameters"]["type"] == "object"
        assert schema["parameters"].get("additionalProperties") is False
        assert schema["description"]
    text = json.dumps(schemas).lower()
    for forbidden in ("token", "workspace_id", "sql"):
        assert forbidden not in text
    reviewer_only = {"approve", "reject", "approve_proposal", "reject_proposal", "edit_proposal"}
    assert reviewer_only.isdisjoint(TOOLS)


def test_get_policy_enforces_access_and_never_infers_the_number(client, guest, agent):
    allowed = received(client, guest)
    result = agent(allowed, "get_policy")
    assert result["ok"] and result["result"]["holder_name"] == "Sam Taylor"

    denied = received(client, guest, policy_number="DEMO-2002")
    result = agent(denied, "get_policy")
    assert result == {
        "ok": False,
        "error": "broker_denied",
        "message": "The broker is not assigned to this policy; stop for review.",
    }
    assert "holder_name" not in json.dumps(result)

    inferred = received(
        client, guest, policy_number=None, original_request="Sam Taylor's email changed."
    )
    result = agent(inferred, "get_policy", {"policy_number": "DEMO-1001"})
    assert result["error"] == "policy_not_stated"
    assert client.get(f"/cases/{inferred}", headers=guest).json()["policy_number"] is None
    assert agent(inferred, "get_policy")["error"] == "missing_policy"

    stated = received(
        client, guest, policy_number=None, original_request="Policy demo-1001: new email."
    )
    result = agent(stated, "get_policy", {"policy_number": "demo-1001"})
    assert result["error"] == "unknown_policy"  # bound verbatim, then looked up as written
    assert client.get(f"/cases/{stated}", headers=guest).json()["policy_number"] == "demo-1001"
    assert agent(allowed, "get_policy", {"policy_number": "DEMO-2002"})["error"] == (
        "policy_mismatch"
    )


def test_check_broker_assignment_reports_without_policy_details(client, guest, agent):
    assert agent(received(client, guest), "check_broker_assignment")["result"] == {
        "broker_id": "broker-alex",
        "policy_number": "DEMO-1001",
        "assigned": True,
    }
    denied = agent(received(client, guest, policy_number="DEMO-2002"), "check_broker_assignment")
    assert denied["result"]["assigned"] is False
    assert "holder" not in json.dumps(denied)
    missing = agent(received(client, guest, policy_number=None), "check_broker_assignment")
    assert missing["error"] == "missing_policy"


def test_inspect_document_binds_only_evidence_of_this_case(client, guest, agent):
    case_id = received(client, guest)
    fixture = agent(case_id, "inspect_document", {"evidence_id": "matching-address"})
    assert fixture["result"]["address"] == "42 Orchard Lane, Demo City, 10001"
    assert client.get(f"/cases/{case_id}", headers=guest).json()["evidence_id"] == (
        "matching-address"
    )

    other_case = received(client, guest)
    foreign = upload_doc(client, guest, other_case, "matching-pdf")
    result = agent(case_id, "inspect_document", {"evidence_id": foreign["id"]})
    assert result["error"] == "evidence_not_found"
    assert client.get(f"/cases/{case_id}", headers=guest).json()["evidence_id"] == (
        "matching-address"
    )
    own = upload_doc(client, guest, case_id, "conflicting-pdf")
    result = agent(case_id, "inspect_document", {"evidence_id": own["id"]})
    assert result["ok"] and result["result"]["source"]["id"] == own["id"]
    assert result["result"]["certain"] is True
    assert agent(case_id, "inspect_document", {"evidence_id": "../etc"})["error"] == (
        "invalid_arguments"
    )


def test_validate_is_a_dry_run(client, guest, agent):
    case_id = received(client, guest)
    result = agent(
        case_id,
        "validate_proposed_changes",
        {"changes": {"mailing_address": "42 Orchard Lane, Demo City, 10001"}},
    )
    assert result["result"]["valid"] is False
    assert [f["code"] for f in result["result"]["findings"]] == ["missing_evidence"]
    case = client.get(f"/cases/{case_id}", headers=guest).json()
    assert case["status"] == "received" and case["proposals"] == []
    assert (
        agent(case_id, "validate_proposed_changes", {"changes": {"plan": "gold"}})["error"]
        == "invalid_arguments"
    )


def test_agent_path_submits_waits_for_human_approval_then_applies(client, guest, agent):
    case_id = received(client, guest)
    assert agent(case_id, "inspect_document", {"evidence_id": "matching-address"})["ok"]
    changes = {
        "mailing_address": "42 Orchard Lane, Demo City, 10001",
        "email": "sam.updated@example.com",
    }
    submitted = agent(case_id, "submit_for_approval", {"changes": changes})
    assert submitted["result"] == {
        "status": "awaiting_approval",
        "version": 1,
        "findings": [],
        "awaiting_approval": True,
    }
    assert agent(case_id, "draft_confirmation")["error"] == "not_completed"
    blocked = agent(case_id, "apply_approved_update", {"version": 1})
    assert blocked["error"] == "http_409"
    assert "requires human approval" in blocked["message"]

    case = client.get(f"/cases/{case_id}", headers=guest).json()
    assert case["proposals"][0]["changes"] == changes
    assert case["requested_changes"] == changes
    assert action(client, guest, case, "approve").status_code == 200

    applied = agent(case_id, "apply_approved_update", {"version": 1})
    assert applied["ok"] and applied["result"]["after"] == changes
    again = agent(case_id, "apply_approved_update", {"version": 1})
    assert again["result"] == applied["result"]
    draft = agent(case_id, "draft_confirmation")["result"]
    assert draft["sent"] is False and draft["confirmation_draft"].startswith("Draft only")
    assert (
        agent(case_id, "inspect_document", {"evidence_id": "matching-address"})["error"]
        == "http_409"
    )

    events = timeline(client, guest, case_id, "tool_called")
    assert [event["details"]["tool"] for event in events] == [
        "inspect_document",
        "submit_for_approval",
        "draft_confirmation",
        "apply_approved_update",
        "apply_approved_update",
        "apply_approved_update",
        "draft_confirmation",
        "inspect_document",
    ]
    assert all(event["actor"] == "agent:agent" for event in events)
    assert events[1]["details"] == {
        "tool": "submit_for_approval",
        "arguments": ["changes"],
        "ok": True,
        "outcome": "ok",
        "case_status": "awaiting_approval",
    }
    assert "Orchard" not in json.dumps([event["details"] for event in events])
    validated = timeline(client, guest, case_id, "proposal_validated")
    assert validated[0]["details"]["source"] == "agent_tool"


def test_follow_up_pauses_the_case_and_a_reply_resumes_it(client, guest, agent):
    case_id = received(client, guest, policy_number=None)
    result = agent(
        case_id,
        "draft_follow_up",
        {"questions": ["Which policy number should be updated?"]},
    )
    assert result["result"]["status"] == "awaiting_information"
    assert "Which policy number should be updated?" in result["result"]["follow_up_draft"]
    assert [f["code"] for f in result["result"]["findings"]] == [
        "clarification_requested",
        "missing_policy",
    ]
    assert action(client, guest, {"id": case_id}, "approve").status_code == 409
    reply = client.post(
        f"/cases/{case_id}/replies",
        headers=guest,
        json={"expected_version": 1, "text": "It is DEMO-1001.", "policy_number": "DEMO-1001"},
    )
    assert reply.status_code == 200
    case = reply.json()
    assert case["current_version"] == 2
    assert [f["code"] for f in case["proposals"][-1]["findings"]] == ["missing_changes"]
    assert agent(case_id, "draft_follow_up", {"questions": []})["error"] == "invalid_arguments"


def test_unknown_tools_and_the_budget_stop_the_loop(client, guest, agent):
    case_id = received(client, guest)
    assert agent(case_id, "approve_proposal", {"version": 1}) == {
        "ok": False,
        "error": "unknown_tool",
        "message": "No tool named approve_proposal",
    }
    assert agent(case_id, "get_policy", {"policy_number": "DEMO-1001", "extra": 1})["error"] == (
        "invalid_arguments"
    )
    with agent.step(case_id, budget=2) as context:
        assert run_tool(context, "check_broker_assignment", None)["ok"]
        assert run_tool(context, "get_policy", None)["ok"]
        with pytest.raises(BudgetExhausted):
            run_tool(context, "get_policy", None)
        assert len(context.calls) == 2
    events = timeline(client, guest, case_id, "tool_called")
    assert [event["details"]["outcome"] for event in events] == [
        "unknown_tool",
        "invalid_arguments",
        "ok",
        "ok",
    ]
    assert client.get(f"/cases/{case_id}", headers=guest).json()["status"] == "received"


def test_tools_reuse_the_api_helpers(client, guest, contact):
    # Structured processing and tool submission produce the same proposal shape.
    case = submit(client, guest, contact)
    assert case["proposals"][0]["changes"] == contact["changes"]
