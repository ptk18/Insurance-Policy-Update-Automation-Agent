"""Transactional domain operations. A caller must supply the authenticated workspace.

Review operations are deliberately separate from execution. Future agent tools must
not expose approve/reject or receive the guest's reviewer credential.
"""

import hashlib
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from policy_update.fixtures import evidence_snapshot
from policy_update.models import (
    Assignment,
    AuditEvent,
    Case,
    Execution,
    Policy,
    Proposal,
    Workspace,
    now,
)
from policy_update.schemas import Intake, ProposalEdit, Reply
from policy_update.validation import validate_changes


class DomainError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_workspace(session: Session) -> tuple[Workspace, str]:
    token = secrets.token_urlsafe(32)
    workspace = Workspace(token_hash=token_hash(token))
    session.add(workspace)
    session.flush()
    for number, name, broker in [
        ("DEMO-1001", "Sam Taylor", "broker-alex"),
        ("DEMO-2002", "Casey Parker", "broker-jordan"),
    ]:
        policy = Policy(
            workspace_id=workspace.id,
            number=number,
            holder_name=name,
            mailing_address="10 Meadow Street, Demo City, 10001",
            email=f"{name.split()[0].lower()}@example.com",
            phone="+1 202 555 0100",
        )
        session.add(policy)
        session.flush()
        session.add(Assignment(policy_id=policy.id, broker_id=broker))
    session.flush()
    return workspace, token


def audit(
    session: Session,
    case: Case,
    actor: str,
    action: str,
    details: dict[str, Any],
    version: int | None = None,
):
    session.add(
        AuditEvent(
            case_id=case.id,
            actor=actor,
            action=action,
            proposal_version=version,
            details=details,
        )
    )


def get_case(session: Session, workspace_id: str, case_id: str) -> Case:
    case = session.scalar(
        select(Case).where(Case.id == case_id, Case.workspace_id == workspace_id).with_for_update()
    )
    if case is None:
        raise DomainError(404, "Case not found")
    return case


def policy_for_case(session: Session, case: Case) -> tuple[Policy | None, str | None]:
    if not case.policy_number:
        return None, "missing_policy"
    policy = session.scalar(
        select(Policy)
        .where(Policy.workspace_id == case.workspace_id, Policy.number == case.policy_number)
        .with_for_update()
    )
    if policy is None:
        return None, "unknown_policy"
    assignment = session.get(Assignment, (policy.id, case.broker_id))
    if assignment is None:
        return None, "broker_denied"
    return policy, None


def get_policy(session: Session, workspace_id: str, number: str, broker_id: str) -> Policy:
    # Reuse the same authorization path as processing; no endpoint bypasses it.
    context = Case(workspace_id=workspace_id, policy_number=number, broker_id=broker_id)
    policy, error = policy_for_case(session, context)
    if error:
        raise DomainError(403 if error == "broker_denied" else 404, "Policy unavailable")
    return policy


def current_proposal(session: Session, case: Case, version: int) -> Proposal:
    if version != case.current_version:
        raise DomainError(409, "Proposal version changed; reload the case")
    proposal = session.scalar(
        select(Proposal).where(Proposal.case_id == case.id, Proposal.version == version)
    )
    if proposal is None:
        raise DomainError(404, "Proposal not found")
    return proposal


def require_editable(case: Case):
    if case.status in {"completed", "rejected", "blocked"}:
        raise DomainError(409, f"A {case.status} case cannot be changed")


def prepare_proposal(session: Session, case: Case, changes: dict[str, str], actor: str) -> Proposal:
    require_editable(case)
    policy, error = policy_for_case(session, case)
    if error == "broker_denied" and case.current_version:
        # Do not turn a previously accessible case into a blocked view that could
        # reveal its old policy snapshots after servicing access is revoked.
        raise DomainError(403, "Policy unavailable")
    evidence = evidence_snapshot(case.evidence_id)
    if error:
        messages = {
            "missing_policy": "Provide the explicit policy number.",
            "unknown_policy": "Provide a known policy number in this sandbox.",
            "broker_denied": "The simulated broker is not assigned to this policy.",
        }
        findings = [{"code": error, "message": messages[error]}]
    else:
        findings = validate_changes(changes, policy, evidence)

    if case.current_version:
        previous = current_proposal(session, case, case.current_version)
        previous.status = "superseded"
    case.current_version += 1
    case.status = (
        "blocked"
        if error == "broker_denied"
        else "awaiting_information"
        if findings
        else "awaiting_approval"
    )
    case.follow_up = (
        "Draft only — please provide the following before this request can proceed: "
        + " ".join(finding["message"] for finding in findings)
        if findings and error != "broker_denied"
        else None
    )
    proposal = Proposal(
        case_id=case.id,
        version=case.current_version,
        changes=changes,
        before={field: getattr(policy, field) for field in changes} if policy else {},
        policy_revision=policy.revision if policy else None,
        findings=findings,
        evidence=evidence,
        status="invalid" if findings else "pending",
    )
    session.add(proposal)
    audit(
        session,
        case,
        actor,
        "proposal_validated",
        {"outcome": case.status, "findings": findings, "source": "structured_review_input"},
        proposal.version,
    )
    session.flush()
    return proposal


def create_case(session: Session, workspace_id: str, data: Intake) -> Case:
    case = Case(
        workspace_id=workspace_id,
        broker_id=data.broker_id,
        policy_number=data.policy_number,
        original_request=data.original_request,
        evidence_id=data.evidence_id,
    )
    session.add(case)
    session.flush()
    actor = f"reviewer:{workspace_id}"
    audit(session, case, actor, "case_created", {"broker_id": case.broker_id})
    prepare_proposal(session, case, data.changes.model_dump(exclude_none=True), actor)
    return case


def edit_proposal(session: Session, case: Case, data: ProposalEdit):
    current_proposal(session, case, data.expected_version)
    return prepare_proposal(
        session, case, data.changes.model_dump(exclude_none=True), f"reviewer:{case.workspace_id}"
    )


def add_reply(session: Session, case: Case, data: Reply):
    require_editable(case)
    previous = current_proposal(session, case, data.expected_version)
    case.replies = [*case.replies, {"text": data.text, "created_at": now()}]
    if data.policy_number is not None:
        case.policy_number = data.policy_number
    if "evidence_id" in data.model_fields_set:
        case.evidence_id = data.evidence_id
    actor = f"reviewer:{case.workspace_id}"
    audit(session, case, actor, "reply_added", {"evidence_id": case.evidence_id})
    return prepare_proposal(session, case, previous.changes, actor)


def recheck(session: Session, case: Case, proposal: Proposal) -> Policy:
    policy, error = policy_for_case(session, case)
    if error:
        raise DomainError(403 if error == "broker_denied" else 409, "Policy unavailable")
    if policy.revision != proposal.policy_revision:
        raise DomainError(409, "Policy changed; prepare a new proposal and obtain fresh approval")
    if evidence_snapshot(case.evidence_id) != proposal.evidence:
        raise DomainError(409, "Evidence changed; prepare a new proposal")
    if validate_changes(proposal.changes, policy, proposal.evidence):
        raise DomainError(409, "Required checks have not passed")
    return policy


def approve(session: Session, case: Case, version: int):
    proposal = current_proposal(session, case, version)
    if case.status != "awaiting_approval" or proposal.status != "pending":
        raise DomainError(409, "Only a valid pending proposal can be approved")
    recheck(session, case, proposal)
    proposal.status = "approved"
    proposal.approved_by = f"reviewer:{case.workspace_id}"
    proposal.approved_at = now()
    case.status = "approved"
    audit(session, case, proposal.approved_by, "proposal_approved", {}, version)
    session.flush()


def reject(session: Session, case: Case, version: int, reason: str):
    require_editable(case)
    proposal = current_proposal(session, case, version)
    proposal.status = "rejected"
    case.status = "rejected"
    audit(
        session,
        case,
        f"reviewer:{case.workspace_id}",
        "proposal_rejected",
        {"reason": reason},
        version,
    )
    session.flush()


def apply_approved_update(session: Session, case: Case, version: int) -> dict[str, Any]:
    proposal = current_proposal(session, case, version)
    # Authorization still applies when returning a previous successful outcome.
    policy, error = policy_for_case(session, case)
    if error:
        raise DomainError(403 if error == "broker_denied" else 409, "Policy unavailable")
    receipt = session.get(Execution, proposal.id)
    if receipt:
        return receipt.result
    if case.status != "approved" or proposal.status != "approved" or not proposal.approved_by:
        raise DomainError(409, "This exact proposal requires human approval before execution")
    policy = recheck(session, case, proposal)
    before = {key: getattr(policy, key) for key in proposal.changes}
    for field, value in proposal.changes.items():
        setattr(policy, field, value)
    # Force revision advancement even if all approved values were already current.
    policy.revision += 1
    session.flush()
    result = {
        "idempotency_key": proposal.id,
        "case_id": case.id,
        "proposal_version": proposal.version,
        "policy_number": policy.number,
        "policy_revision": policy.revision,
        "before": before,
        "after": proposal.changes,
        "executed_at": now(),
    }
    session.add(Execution(proposal_id=proposal.id, result=result))
    proposal.status = "applied"
    case.status = "completed"
    case.confirmation = (
        f"Draft only — policy {policy.number} has been updated following human approval: "
        + "; ".join(f"{key.replace('_', ' ')}: {value}" for key, value in proposal.changes.items())
        + ". No email has been sent."
    )
    audit(session, case, "system:simulated-policy-api", "update_applied", result, version)
    audit(session, case, "system:draft-template", "confirmation_drafted", {}, version)
    session.flush()
    # The request transaction commits policy, receipt, case, and audit together.
    return result


def policy_view(policy: Policy):
    return {
        key: getattr(policy, key)
        for key in ("number", "holder_name", "mailing_address", "email", "phone", "revision")
    }


def case_view(session: Session, case: Case):
    # Fail closed if a servicing assignment is removed after proposal preparation.
    _, access_error = policy_for_case(session, case)
    if access_error == "broker_denied" and case.status != "blocked":
        raise DomainError(403, "Policy unavailable")
    proposals = session.scalars(
        select(Proposal).where(Proposal.case_id == case.id).order_by(Proposal.version)
    ).all()
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.case_id == case.id)
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
    return {
        "id": case.id,
        "broker_id": case.broker_id,
        "policy_number": case.policy_number,
        "original_request": case.original_request,
        "replies": case.replies,
        "evidence_id": case.evidence_id,
        "status": case.status,
        "current_version": case.current_version,
        "follow_up_draft": case.follow_up,
        "confirmation_draft": case.confirmation,
        "created_at": case.created_at,
        "proposals": [
            {
                key: getattr(proposal, key)
                for key in (
                    "id",
                    "version",
                    "changes",
                    "before",
                    "policy_revision",
                    "findings",
                    "evidence",
                    "status",
                    "approved_by",
                    "approved_at",
                    "created_at",
                )
            }
            for proposal in proposals
        ],
        "timeline": [
            {
                key: getattr(event, key)
                for key in ("id", "actor", "action", "proposal_version", "details", "created_at")
            }
            for event in events
        ],
    }
