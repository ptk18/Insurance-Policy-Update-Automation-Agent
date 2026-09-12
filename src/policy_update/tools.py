"""Typed, case-scoped tools for the bounded agent (task A02).

Every tool runs against one already-authorized case inside the caller's transaction and
delegates to the same service functions the review API uses, so sandbox isolation,
broker authorization, permitted fields, evidence prerequisites, approval versions, and
idempotent execution are enforced here exactly as everywhere else. Reviewer operations
(approve, reject, edit) and the guest's bearer token are intentionally not reachable.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field, ValidationError
from sqlalchemy.orm import Session

from policy_update import service
from policy_update.extraction import confirm_verbatim
from policy_update.models import Case
from policy_update.schemas import Changes, EvidenceId, StrictModel
from policy_update.validation import validate_changes

DEFAULT_TOOL_BUDGET = 12


class ToolError(Exception):
    """A tool result the model should observe, never a crash: ``code`` is stable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class BudgetExhausted(Exception):
    pass


class NoInput(StrictModel):
    pass


class PolicyInput(StrictModel):
    policy_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Only needed when the case has no policy number yet; it must be "
        "stated verbatim in the request text.",
    )


class DocumentInput(StrictModel):
    evidence_id: EvidenceId = Field(
        description="A server-owned evidence fixture name or the ID of an attachment "
        "uploaded to this case."
    )


class ChangesInput(StrictModel):
    changes: Changes


class FollowUpInput(StrictModel):
    changes: Changes | None = Field(
        default=None, description="The changes understood so far, if any."
    )
    questions: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Plain questions for the broker, one per missing or unclear item.",
    )


class VersionInput(StrictModel):
    version: int = Field(ge=1, description="The exact proposal version a human approved.")


@dataclass
class ToolContext:
    session: Session
    case: Case
    actor: str = "agent"
    budget: int = DEFAULT_TOOL_BUDGET
    calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[StrictModel]
    handler: Callable[[ToolContext, Any], dict[str, Any]]

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_model.model_json_schema(),
        }


def _request_text(case: Case) -> str:
    return "\n".join([case.original_request, *(reply["text"] for reply in case.replies)])


def _access_error(error: str) -> ToolError:
    messages = {
        "missing_policy": "No policy number is known for this case; ask the broker for it.",
        "unknown_policy": "That policy number does not exist in this sandbox.",
        "broker_denied": "The broker is not assigned to this policy; stop for review.",
    }
    return ToolError(error, messages[error])


def get_policy(context: ToolContext, data: PolicyInput) -> dict[str, Any]:
    case = context.case
    if case.policy_number is None and data.policy_number is not None:
        # Binding is allowed only for a number the broker actually wrote, so the
        # model cannot resolve a missing number from a name or a guess.
        if confirm_verbatim("policy_number", data.policy_number, _request_text(case)):
            raise ToolError(
                "policy_not_stated",
                "That policy number does not appear in the request; it stays unresolved.",
            )
        case.policy_number = data.policy_number
    elif data.policy_number is not None and data.policy_number != case.policy_number:
        raise ToolError("policy_mismatch", "This case is bound to a different policy number.")
    policy, error = service.policy_for_case(context.session, case)
    if error:
        raise _access_error(error)
    return service.policy_view(policy)


def check_broker_assignment(context: ToolContext, _data: NoInput) -> dict[str, Any]:
    _, error = service.policy_for_case(context.session, context.case)
    if error in {"missing_policy", "unknown_policy"}:
        raise _access_error(error)
    return {
        "broker_id": context.case.broker_id,
        "policy_number": context.case.policy_number,
        "assigned": error is None,
    }


def inspect_document(context: ToolContext, data: DocumentInput) -> dict[str, Any]:
    case = context.case
    _domain(lambda: service.require_editable(case))
    previous = case.evidence_id
    case.evidence_id = data.evidence_id
    try:
        evidence = service.resolve_evidence(context.session, case)
    except service.DomainError as error:
        case.evidence_id = previous
        raise ToolError("evidence_not_found", error.detail) from error
    # Inspecting binds the evidence the later validation and proposal will snapshot.
    return {"evidence_id": data.evidence_id, **evidence}


def validate_proposed_changes(context: ToolContext, data: ChangesInput) -> dict[str, Any]:
    case = context.case
    policy, error = service.policy_for_case(context.session, case)
    if error:
        raise _access_error(error)
    changes = data.changes.model_dump(exclude_none=True)
    findings = validate_changes(changes, policy, service.resolve_evidence(context.session, case))
    return {"changes": changes, "valid": not findings, "findings": findings}


def draft_follow_up(context: ToolContext, data: FollowUpInput) -> dict[str, Any]:
    changes = data.changes.model_dump(exclude_none=True) if data.changes else {}
    notes = [
        {"code": "clarification_requested", "message": " ".join(question.split())[:300]}
        for question in data.questions
    ]
    proposal = _prepare(context, changes, notes)
    return {
        "status": context.case.status,
        "version": proposal.version,
        "follow_up_draft": context.case.follow_up,
        "findings": proposal.findings,
    }


def submit_for_approval(context: ToolContext, data: ChangesInput) -> dict[str, Any]:
    proposal = _prepare(context, data.changes.model_dump(exclude_none=True), None)
    return {
        "status": context.case.status,
        "version": proposal.version,
        "findings": proposal.findings,
        "awaiting_approval": context.case.status == "awaiting_approval",
    }


def apply_approved_update(context: ToolContext, data: VersionInput) -> dict[str, Any]:
    return _domain(
        lambda: service.apply_approved_update(context.session, context.case, data.version)
    )


def draft_confirmation(context: ToolContext, _data: NoInput) -> dict[str, Any]:
    case = context.case
    if case.status != "completed" or not case.confirmation:
        raise ToolError("not_completed", "No approved update has been applied yet.")
    return {"confirmation_draft": case.confirmation, "sent": False}


def _prepare(context: ToolContext, changes: dict[str, str], notes):
    case = context.case

    def operation():
        case.requested_changes = changes
        # The first proposal also carries what extraction could not handle, so an
        # unsupported or ambiguous request pauses for review even if the model
        # chose to submit only the permitted part.
        pending = (
            service.extraction_findings(context.session, case) if not case.current_version else []
        )
        return service.prepare_proposal(
            context.session,
            case,
            changes,
            f"agent:{context.actor}",
            [*(notes or []), *pending] or None,
            "agent_tool",
        )

    return _domain(operation)


def _domain(operation):
    try:
        return operation()
    except service.DomainError as error:
        raise ToolError(f"http_{error.status}", error.detail) from error


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in [
        ToolSpec(
            "get_policy",
            "Retrieve the policy this case may service. Fails without revealing details "
            "when the number is missing, unknown, or not assigned to the broker.",
            PolicyInput,
            get_policy,
        ),
        ToolSpec(
            "check_broker_assignment",
            "Check whether the case's broker is assigned to service its policy.",
            NoInput,
            check_broker_assignment,
        ),
        ToolSpec(
            "inspect_document",
            "Inspect proof-of-address evidence (fixture name or attachment ID of this case) "
            "and bind it to the case. Returns extracted name/address, certainty, reasons, "
            "and the page reference.",
            DocumentInput,
            inspect_document,
        ),
        ToolSpec(
            "validate_proposed_changes",
            "Dry-run validation of mailing address, email, or phone changes against the "
            "policy and bound evidence. Creates nothing.",
            ChangesInput,
            validate_proposed_changes,
        ),
        ToolSpec(
            "draft_follow_up",
            "Prepare a clarification draft for the broker and pause the case as "
            "awaiting information. Nothing is sent.",
            FollowUpInput,
            draft_follow_up,
        ),
        ToolSpec(
            "submit_for_approval",
            "Create a versioned proposal for human approval. Any failed check pauses the "
            "case instead; approval itself is a human action outside these tools.",
            ChangesInput,
            submit_for_approval,
        ),
        ToolSpec(
            "apply_approved_update",
            "Apply the exact proposal version a human approved through the simulated "
            "policy API. Repeating it returns the saved receipt.",
            VersionInput,
            apply_approved_update,
        ),
        ToolSpec(
            "draft_confirmation",
            "Return the confirmation draft for a completed update. Nothing is sent.",
            NoInput,
            draft_confirmation,
        ),
    ]
}


def tool_schemas() -> list[dict[str, Any]]:
    return [spec.schema() for spec in TOOLS.values()]


def run_tool(context: ToolContext, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Validate, execute, and audit one tool call. Returns ``{"ok": True, "result": ...}``
    or ``{"ok": False, "error": code, "message": ...}``; raises ``BudgetExhausted`` when
    the bounded call budget is spent so the loop stops for review."""
    if len(context.calls) >= context.budget:
        raise BudgetExhausted(f"Tool budget of {context.budget} calls exhausted")
    spec = TOOLS.get(name)
    outcome: dict[str, Any]
    if spec is None:
        outcome = {"ok": False, "error": "unknown_tool", "message": f"No tool named {name}"}
    else:
        try:
            data = spec.input_model.model_validate(arguments or {})
            outcome = {"ok": True, "result": spec.handler(context, data)}
        except ValidationError as error:
            outcome = {
                "ok": False,
                "error": "invalid_arguments",
                "message": "; ".join(
                    f"{'.'.join(str(part) for part in item['loc']) or 'input'}: {item['msg']}"
                    for item in error.errors()
                ),
            }
        except ToolError as error:
            outcome = {"ok": False, "error": error.code, "message": error.message}
    record = {
        "tool": name,
        "arguments": sorted(arguments or {}),
        "ok": outcome["ok"],
        "outcome": "ok" if outcome["ok"] else outcome["error"],
        "case_status": context.case.status,
    }
    context.calls.append(record)
    # Argument names and outcome only: values already live in proposals, not audit logs.
    service.audit(context.session, context.case, f"agent:{context.actor}", "tool_called", record)
    return outcome
