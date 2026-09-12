"""Transactional domain operations. A caller must supply the authenticated workspace.

Review operations are deliberately separate from execution. Future agent tools must
not expose approve/reject or receive the guest's reviewer credential.
"""

import hashlib
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from policy_update.documents import inspect_document, safe_filename, sniff_content_type
from policy_update.extraction import ModelClient, ModelError, extract_request
from policy_update.fixtures import EVIDENCE, evidence_snapshot
from policy_update.models import (
    Assignment,
    Attachment,
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
    if not case.current_version:
        raise DomainError(409, "This case has not been processed yet")
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


def get_attachment(session: Session, case: Case, attachment_id: str) -> Attachment:
    # Scoped to the case, which the caller already resolved within its workspace.
    attachment = session.scalar(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.case_id == case.id,
            Attachment.workspace_id == case.workspace_id,
        )
    )
    if attachment is None:
        raise DomainError(404, "Attachment not found")
    return attachment


def resolve_evidence(session: Session, case: Case) -> dict[str, Any] | None:
    """Evidence is either a server-owned fixture or an attachment of this same case."""
    if case.evidence_id is None:
        return None
    if case.evidence_id in EVIDENCE:
        return evidence_snapshot(case.evidence_id)
    return get_attachment(session, case, case.evidence_id).inspection


def store_attachment(
    session: Session, case: Case, filename: str | None, content: bytes, limit: int
) -> Attachment:
    require_editable(case)
    if len(content) > limit:
        raise DomainError(413, f"Attachments are limited to {limit} bytes")
    if not content:
        raise DomainError(422, "The uploaded file is empty")
    content_type = sniff_content_type(content)
    if content_type is None:
        raise DomainError(415, "Only PDF, PNG, and JPEG attachments are accepted")
    attachment = Attachment(
        workspace_id=case.workspace_id,
        case_id=case.id,
        filename=safe_filename(filename),
        content_type=content_type,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        content=content,
        inspection={},
    )
    session.add(attachment)
    session.flush()
    attachment.inspection = inspect_document(
        content,
        content_type,
        {"id": attachment.id, "filename": attachment.filename, "content_type": content_type},
    )
    # An upload before processing is the evidence the first proposal will inspect.
    # Later uploads are bound explicitly through a reply so the case is revalidated.
    bound = case.status == "received"
    if bound:
        case.evidence_id = attachment.id
    audit(
        session,
        case,
        f"reviewer:{case.workspace_id}",
        "attachment_uploaded",
        {
            "attachment_id": attachment.id,
            "content_type": content_type,
            "size": attachment.size,
            "readable": attachment.inspection["readable"],
            "certain": attachment.inspection["certain"],
            "bound_as_evidence": bound,
        },
    )
    session.flush()
    return attachment


def prepare_proposal(
    session: Session,
    case: Case,
    changes: dict[str, str],
    actor: str,
    notes: list[dict[str, str]] | None = None,
    source: str = "structured_review_input",
) -> Proposal:
    """``notes`` are extra findings (for example unsupported or ambiguous wording found by
    request extraction) that pause the case alongside the domain validation."""
    require_editable(case)
    policy, error = policy_for_case(session, case)
    if error == "broker_denied" and case.current_version:
        # Do not turn a previously accessible case into a blocked view that could
        # reveal its old policy snapshots after servicing access is revoked.
        raise DomainError(403, "Policy unavailable")
    evidence = resolve_evidence(session, case)
    if error:
        messages = {
            "missing_policy": "Provide the explicit policy number.",
            "unknown_policy": "Provide a known policy number in this sandbox.",
            "broker_denied": "The simulated broker is not assigned to this policy.",
        }
        findings = [{"code": error, "message": messages[error]}]
    else:
        findings = validate_changes(changes, policy, evidence)
    if notes and error != "broker_denied":
        findings = [*notes, *findings]

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
        {"outcome": case.status, "findings": findings, "source": source},
        proposal.version,
    )
    session.flush()
    return proposal


def create_case(session: Session, workspace_id: str, data: Intake) -> Case:
    """Persist intake only. Policy lookup, authorization, and validation happen in
    ``process_case`` so a stored request survives a processing failure and a future
    inbox adapter or worker can submit and process the same structure."""
    case = Case(
        workspace_id=workspace_id,
        broker_id=data.broker_id,
        policy_number=data.policy_number,
        original_request=data.original_request,
        evidence_id=data.evidence_id,
        requested_changes=data.changes.model_dump(exclude_none=True) if data.changes else None,
    )
    session.add(case)
    session.flush()
    audit(
        session,
        case,
        f"reviewer:{workspace_id}",
        "case_created",
        {"broker_id": case.broker_id, "source": "structured_intake"},
    )
    return case


def process_case(session: Session, case: Case, model: ModelClient | None = None) -> Proposal:
    # Synchronous stand-in for the planned worker; the row lock taken by get_case plus
    # the received-only guard keep concurrent processing single-shot.
    if case.status != "received":
        raise DomainError(409, "This case has already been processed")
    if case.requested_changes is not None or model is None:
        return prepare_proposal(
            session, case, case.requested_changes or {}, "system:structured-processing"
        )
    return process_free_text(session, case, model)


def process_free_text(session: Session, case: Case, model: ModelClient) -> Proposal:
    """Extract the request with the hosted model, then validate exactly as structured
    intake. A model failure leaves the case ``received`` so processing can be retried."""
    try:
        extraction = extract_request(model, case.original_request)
    except ModelError as error:
        raise DomainError(
            503 if error.retryable else 502,
            "Request extraction is unavailable; the case is still received and can be "
            "processed again"
            if error.retryable
            else "Request extraction failed; check the model configuration or submit a "
            "new case with structured changes",
        ) from error
    # The policy number is only ever the one stated in the text, never one inferred
    # from the requester's or policyholder's name.
    if case.policy_number is None and extraction.policy_number is not None:
        case.policy_number = extraction.policy_number
    case.requested_changes = extraction.changes
    audit(
        session,
        case,
        f"model:{model.name}",
        "request_extracted",
        extraction.summary(),
    )
    return prepare_proposal(
        session,
        case,
        extraction.changes,
        "system:model-extraction",
        notes=extraction.findings(),
        source="model_extraction",
    )


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
    if resolve_evidence(session, case) != proposal.evidence:
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


def attachment_view(attachment: Attachment):
    return {
        key: getattr(attachment, key)
        for key in (
            "id",
            "case_id",
            "filename",
            "content_type",
            "size",
            "sha256",
            "inspection",
            "created_at",
        )
    }


def case_view(session: Session, case: Case):
    # Fail closed if a servicing assignment is removed after proposal preparation.
    # Unprocessed and blocked cases hold no policy snapshot, so they stay readable.
    _, access_error = policy_for_case(session, case)
    if access_error == "broker_denied" and case.status not in {"received", "blocked"}:
        raise DomainError(403, "Policy unavailable")
    proposals = session.scalars(
        select(Proposal).where(Proposal.case_id == case.id).order_by(Proposal.version)
    ).all()
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.case_id == case.id)
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ).all()
    attachments = session.scalars(
        select(Attachment)
        .where(Attachment.case_id == case.id, Attachment.workspace_id == case.workspace_id)
        .order_by(Attachment.created_at, Attachment.id)
    ).all()
    return {
        "id": case.id,
        "broker_id": case.broker_id,
        "policy_number": case.policy_number,
        "original_request": case.original_request,
        "replies": case.replies,
        "evidence_id": case.evidence_id,
        "requested_changes": case.requested_changes,
        "attachments": [attachment_view(attachment) for attachment in attachments],
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
