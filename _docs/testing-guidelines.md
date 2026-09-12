# Testing guidelines and coverage inventory

Last inspected: 2026-09-12. Read this file before adding or changing tests.
Delivery tasks are tracked in [process.md](process.md); acceptance criterion numbers
below refer to [plan.md](plan.md).

## What exists today

[test_workflow.py](../tests/test_workflow.py) contains **19 test functions, producing
26 cases after parameterization**. They exercise the FastAPI API with a real
SQLAlchemy database through TestClient. There are no frontend, document-extraction,
LangGraph, or hosted-model tests yet. This is a behavior inventory, not a measured
line/branch coverage report.

The previous backend build session ran all 26 cases successfully on SQLite and
PostgreSQL, plus lint/format checks and the three live API smoke scenarios.
This documentation update inventories source assertions; it does not represent a
new database test run. CI is configured, but a hosted run has not been verified.

## Find existing coverage

All test names below are in [test_workflow.py](../tests/test_workflow.py). Use an
exact name with `pytest tests/test_workflow.py::TEST_NAME`, or a keyword group from
the commands below. Extend an existing scenario when it already owns the behavior.

### Successful updates and validation — criteria 3, 4, 5, 8

- `test_contact_approval_execution_and_retry` — **1 case.** Email-only input reaches
  review without evidence; execution before approval fails; approval records a
  reviewer; execution changes the policy once; retry returns the same result;
  completion includes an unsent confirmation and one versioned update audit event.
- `test_unresolved_evidence_blocks_whole_request_and_corrected_reply_resumes` —
  **4 cases:** absent evidence, conflicting address, wrong name, and unreadable
  evidence. Each blocks approval/execution and leaves the accompanying email
  unchanged. A matching replacement fixture clears the draft, supersedes version
  1, creates version 2 with a page reference, and allows approval/address execution.
- `test_harmless_evidence_formatting_is_accepted` — **1 case.** Uppercase, newline,
  and punctuation differences in the requested address still pass fixture checks.
- `test_missing_or_unknown_policy_requires_explicit_reply` — **2 cases:** missing
  and unknown policy number. Both pause without before-values and block approval;
  an explicit valid number in a structured reply allows review.
- `test_rejects_unsupported_or_empty_changes` — **3 cases:** an unsupported
  `coverage` field, empty changes, and null email. Each returns 422 and creates no case.
- `test_invalid_contact_format_requires_clarification` — **2 cases:** malformed
  email and short phone number. Each pauses and blocks approval.

### Approval and stale state — criteria 7, 9

- `test_edit_invalidates_approval_and_stale_browser_actions` — **1 case.** Editing an
  approved email proposal to a phone change supersedes the approval. Old-version
  edit/approval/execution and unapproved new-version execution fail. Fresh approval
  allows execution and the discarded email change is not applied.
- `test_reply_after_approval_requires_fresh_approval` — **1 case.** Replacing matching
  evidence with a wrong-name fixture after approval creates an unresolved version;
  old-version execution and new-version approval fail.
- `test_two_cases_cannot_execute_against_the_same_policy_revision` — **1 case.** Two
  cases approved against one revision execute sequentially; the second becomes
  stale. Refreshing its proposal still requires fresh approval before execution.
- `test_policy_change_before_approval_is_rechecked` — **1 case.** One case's update
  makes a second pending proposal stale, so approval of the second fails.
- `test_rejection_is_terminal` — **1 case.** Rejection persists the rejected status
  and blocks approval/execution. It does not enumerate every terminal-state route.

### Authentication, authorization, and isolation — criteria 1, 6, 11, 12

- `test_authentication_required` — **1 case.** Case listing and fixtures require
  authentication; case listing rejects an invalid bearer token. This is not an
  exhaustive missing-token check on every route.
- `test_unassigned_broker_cannot_inspect_approve_or_execute` — **1 case.** The wrong
  seeded broker gets a blocked case without policy before-values; direct policy
  lookup, approval, execution, and proposal editing are denied.
- `test_guest_isolation_for_every_case_endpoint` — **1 case.** A second guest cannot
  list, read, edit, reply to, approve, reject, or execute the first guest's case.
  Updating the first guest's policy does not change the second guest's seeded copy.
  There are no attachment endpoints to test yet.
- `test_request_text_cannot_supply_approval_or_authorization` — **1 case.** A raw
  instruction-like request remains pending and cannot execute without approval.
  An extra `approved_by` input is rejected and its raw value is omitted from the
  validation error. No LLM interprets the request; this is not an LLM injection test.
- `test_revoked_assignment_blocks_existing_case_access_and_execution` — **1 case.**
  Removing the servicing assignment after approval blocks detail, execution, edit,
  and reply operations, including attempts to reopen old proposal values.

### Persistence, concurrency, and failure recovery — criteria 8, 9, 10

- `test_paused_case_approval_and_receipt_survive_restart` — **1 case.** Recreates
  application instances against a temporary SQLite file at awaiting-approval,
  approved, and completed stages. The token remains usable and execution replay
  preserves the receipt/revision. This is app recreation, not a killed worker or
  PostgreSQL server restart; awaiting-information and LangGraph are not exercised.
- `test_failure_between_policy_write_and_audit_rolls_back` — **1 case.** Injects an
  exception at the update-audit call after the policy flush. The API fails, policy
  values and approval state remain intact, no confirmation appears, and retry
  succeeds. It does not simulate a process crash or every commit failure window.
- `test_concurrent_execution_has_one_persisted_outcome` — **1 case.** Two threads
  submit the same approved execution. Responses may be success or conflict; replay
  succeeds and the database has one update event, one keyed receipt, and one
  revision increment. Scheduling is not forced to hit a specific race window.

## Fixtures, databases, and smoke scenarios

[conftest.py](../tests/conftest.py) provides `app`, `client`, `guest`, `contact`, and
`address`. Each test gets a fresh guest. SQLite uses a temporary file by default.
`TEST_DATABASE_URL` selects a dedicated PostgreSQL database for the shared API
suite; the explicit restart test always uses SQLite. PostgreSQL tests leave
synthetic rows, so never point this variable at production/shared business data.

[fixtures.py](../src/policy_update/fixtures.py) provides four evidence dictionaries
and four sample requests. `unreadable` sets both `readable` and `certain` to false;
there is no separate readable-but-uncertain fixture. Source page 1 is fixture
metadata, not proof of page extraction. Fixture consistency does not establish
document authenticity.

[scripts/demo.py](../scripts/demo.py) uses a running local server to exercise
contact-only, missing evidence/correction, and conflicting evidence/correction.
Each scenario approves through the API and checks duplicate execution. This is a
manual smoke companion, not pytest, browser automation, or an autonomous agent.
It creates synthetic records and performs simulated approvals/updates.

## Commands

Run from the repository root:

```sh
uv sync --locked
uv run pytest --collect-only -q
uv run pytest -q --tb=short
uv run pytest -q --tb=short -k 'evidence or contact or policy'
uv run pytest -q --tb=short -k 'approval or stale or rejection'
uv run pytest -q --tb=short -k 'guest or broker or assignment or authentication'
uv run pytest -q --tb=short -k 'restart or failure or concurrent'
uv run ruff check .
uv run ruff format --check .
```

Keyword groups overlap intentionally. For a persistence/concurrency change, also
run the suite with `TEST_DATABASE_URL` configured for a dedicated UTF-8 PostgreSQL
test database. Keep credentials out of commands copied into documentation/logs.
The [CI workflow](../.github/workflows/ci.yml) runs Python 3.12, lint/format checks,
then SQLite and PostgreSQL 17 tests.

For a smoke check, start the API with the README command and run
`uv run python scripts/demo.py` separately. Do not start a server or perform paid
model calls for a documentation-only change.

## How to add useful tests

1. Find the matching inventory entry and acceptance criterion. Reuse fixtures and
   parameterize equivalent input branches; avoid duplicate happy-path scenarios.
2. Test observable behavior and durable state. For denied writes, assert both the
   response and unchanged values/no execution outcome where relevant.
3. Keep database constraints and transactions real in persistence tests. Use
   isolated guests; do not mock away the control the test is meant to verify.
4. Use deterministic failure injection or model fakes for regression checks.
   Verify public tool permissions and outcomes, not hidden reasoning or one exact
   wording/tool sequence. Keep paid model evaluation separate and explicitly authorized.
5. Add targeted regression coverage for a discovered failure. Test only meaningful
   behavior, not trivial implementation details or documentation wording.
6. Run affected checks, broaden when the change warrants it, then update this
   inventory with exact test names, case counts, assertions, and remaining gaps.

For UI changes, follow [design-system.md](design-system.md), verify the user flow
and relevant screenshots, and record the viewport/state checked. UI tooling has
not been selected or installed yet.

## Coverage to add as implementation proceeds

### Existing backend gaps

- [ ] Dedicated readable-but-uncertain and missing extracted-field cases; broader
  normalization examples that must remain conflicting rather than match loosely.
- [ ] Explicit combined address/email/phone execution and contact-field boundary
  cases when those paths change; the suite does not enumerate every combination.
- [ ] Awaiting-information app restart and persisted replies/evidence history;
  reply with unchanged evidence and explicit evidence removal after approval.
- [ ] Revocation before approval and after successful execution/replay; evidence
  snapshot changes before approval/execution; all terminal edit/reply paths.
- [ ] Controlled interleavings for competing edits/approvals/replies and different
  cases updating one policy; the existing different-case stale test is sequential.
- [ ] Additional relevant transaction failure windows and log-redaction assertions.
  Existing error-response checks do not prove all application logs are safe.

### Features not yet implemented

- [ ] E02–E06: real PDF/image parsing, source fidelity, private attachment ownership,
  type/size validation, unreadable/conflicting uploads, and corrected documents.
- [ ] B13/A01–A08: intake/job separation, typed tools and permission enforcement,
  tool budgets, genuine selection, human interrupts, checkpoint recovery, temporary
  failure retry, and adversarial email/document inputs.
- [ ] U01–U07: browser session isolation, actual review/approval flows, stale-state
  feedback, draft labeling, accessible interactions, and visual regression checks.
- [ ] V05–V08: migrations with retained records, guest expiry/limits/cleanup,
  private storage configuration, worker/host restart, and hosted smoke checks.
- [ ] V09: separately measured synthetic model extraction and end-to-end outcomes.

These gaps are not a request to write speculative tests before their feature
exists. Add coverage alongside the behavior or when a concrete risk is investigated.
