# Testing guidelines and coverage inventory

Last inspected: 2026-09-13 (migrations, public-demo controls, broader UI checks). Read
this file before adding or changing tests. Delivery tasks are tracked in
[process.md](process.md); acceptance criterion numbers below refer to
[plan.md](plan.md).

## What exists today

[test_workflow.py](../tests/test_workflow.py) (22 functions / 29 cases),
[test_attachments.py](../tests/test_attachments.py) (7 functions / 11 cases),
[test_extraction.py](../tests/test_extraction.py) (12 functions / 20 cases),
[test_tools.py](../tests/test_tools.py) (9 functions / 9 cases),
[test_agent.py](../tests/test_agent.py) (11 functions / 15 cases),
[test_worker.py](../tests/test_worker.py) (9 functions / 9 cases), and
[test_adversarial.py](../tests/test_adversarial.py) (4 functions / 4 cases), and
[test_operations.py](../tests/test_operations.py) (9 functions / 9 cases) total **83
test functions, producing 106 cases after parameterization**. They exercise the FastAPI
API with a real SQLAlchemy database through TestClient. Hosted-model behavior is covered
only through scripted fakes and a mocked HTTP transport; there are no live-model or
image-inspection tests in that Python inventory. A separate frontend browser suite is
described below. This is a behavior inventory, not a measured line/branch coverage
report.

Current verification results are recorded in
[process.md](process.md#latest-verification--2026-09-13). The inventory below describes
assertions, not hosted acceptance or measured model accuracy.

[helpers.py](../tests/helpers.py) provides `run` (queue `process`/`resume`/`retry`
for a case expecting `202`, run the app's worker inline with `drain`, and return the
stored case), `submit` (intake expecting `received`, then `run`), `drain`, `action`,
`policy`, `upload_doc`, and `FakeModel`/`answer` (a scripted extraction model) and
`FakeChat`/`call`/`stop` (a scripted tool-selection model that keeps every prompt
it saw; a queued callable runs as a hook between decisions); unscripted calls fail
loudly. An autouse fixture points `.env` loading at a missing file, clears
`GEMINI_API_KEY`, and sets `WORKER_MODE=external`, so even a bare `create_app()` in
a test cannot go live or start a background worker thread; tests drive
`app.state.worker` themselves and stay deterministic. `conftest.py` builds the app
with `model=None`, so the suite never loads `.env` or calls a hosted model;
extraction tests override `app` with a `FakeModel`. Use `submit` unless a test is
about the intake/queue/worker boundary.
`test_attachments.py` adds local `sample`, `upload`, `reply_with`, and `intake`
helpers.

## Find existing coverage

Test names below are in [test_workflow.py](../tests/test_workflow.py) unless a
section says otherwise. Use an
exact name with `pytest tests/test_workflow.py::TEST_NAME`, or a keyword group from
the commands below. Extend an existing scenario when it already owns the behavior.

### Intake and processing separation — criteria 4, 10 (B13)

- `test_intake_is_persisted_before_processing` — **1 case.** Intake returns a
  `received` case with version 0, no proposals, stored `requested_changes`, and a
  `case_created` event; it appears in the list. Approve, execute, reject, reply, and
  edit all return 409 before processing. `/process` answers 202 with the case still
  `received` and its job `queued` (no worker yet); a second call while queued is
  409; one worker pass runs exactly that job and yields `awaiting_approval` with
  the stored changes, `processing_queued`/`proposal_validated`/`processing_finished`
  events, and a `waiting` job owned by the app's worker; a later process call is
  409 and a further worker pass runs nothing.
- `test_processing_failure_keeps_intake_retryable` — **1 case.** Injects an
  exception in validation while the worker runs the job. Queueing succeeded (202);
  the case stays `received` with no proposal and its requested changes intact; the
  job is `failed`/retryable with `processing_failed`; a retry processes it
  normally with `attempts` 2. This is a crash inside the worker's attempt, not a
  killed worker (see test_worker.py for lapsed leases).
- `test_intake_without_changes_pauses_until_reviewer_supplies_them` — **1 case.**
  Intake without `changes` processes to `awaiting_information` with only a
  `missing_changes` finding, empty proposal changes, and a draft; approval fails.
  A reviewer edit creates version 2, which can be approved and executed.

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
  seeded broker's intake is stored as `received` without revealing policy values;
  processing yields a blocked case without before-values; direct policy lookup,
  approval, execution, and proposal editing are denied.
- `test_guest_isolation_for_every_case_endpoint` — **1 case.** A second guest cannot
  list, read, edit, reply to, approve, reject, execute, or process the first guest's
  case. Updating the first guest's policy does not change the second guest's seeded
  copy. Attachment isolation is covered separately in test_attachments.py.
- `test_request_text_cannot_supply_approval_or_authorization` — **1 case.** A raw
  instruction-like request remains pending and cannot execute without approval.
  An extra `approved_by` input is rejected and its raw value is omitted from the
  validation error. No LLM interprets the request; this is not an LLM injection test.
- `test_revoked_assignment_blocks_existing_case_access_and_execution` — **1 case.**
  Removing the servicing assignment after approval blocks detail, execution, edit,
  and reply operations, including attempts to reopen old proposal values.

### Uploaded documents and inspection — criteria 4, 5, 6, 11, 12 (E02–E06)

All in [test_attachments.py](../tests/test_attachments.py). Inspection assertions cover
the PDF text layer only; image documents are asserted to be _uncertain_, not inspected.

- `test_fixture_documents_are_listed_and_downloadable` — **1 case.** `GET /fixtures`
  lists every sample document with type/size; each download matches; downloads
  require authentication; unknown IDs are 404.
- `test_uploaded_pdf_is_inspected_with_page_reference_and_supports_execution` —
  **1 case.** A two-page matching PDF uploaded to a `received` case is sanitized
  (`../My Bill (Aug).PDF` → `My_Bill__Aug_.PDF`), typed from bytes, inspected with
  name/address and `page: 2`, bound as evidence, audited without extracted values,
  retrievable byte-for-byte with `private, no-store`, and processed to
  `awaiting_approval`; approval and address execution succeed.
- `test_unresolved_document_blocks_and_corrected_upload_resumes` — **5 cases:**
  conflicting address, wrong name, scanned (no text layer), readable without labeled
  fields, and PNG image. Each processes to `awaiting_information` with the expected
  finding and the inspection reason inside the message; approval fails. A later
  matching upload does not change the case until a reply binds it, which supersedes
  version 1, keeps both attachment references, and allows approval/execution.
- `test_embedded_document_instructions_only_yield_labeled_fields` — **1 case.** A
  matching PDF containing instruction text is certain, its inspection carries no
  instruction text, execution still needs approval, and the other broker stays denied.
- `test_upload_validation_rejects_wrong_type_size_and_state` — **1 case.** Uses a
  1500-byte limit app: plain text is 415, a PNG-magic body is accepted as `image/png`
  regardless of filename, empty is 422, oversized is 413, a broken PDF is stored
  with an unreadable reason, an unknown case is 404, and a completed case is 409.
- `test_attachments_are_isolated_by_workspace_and_case` — **1 case.** Another guest
  cannot read, download, or upload to the case (404; missing token 401), and neither
  another guest's case nor a sibling case in the same workspace can bind the
  attachment or an unknown evidence name as evidence (404, version unchanged).
- `test_attachment_and_binding_survive_restart` — **1 case.** After app recreation
  over SQLite the attachment bytes and the `received` case's evidence binding remain
  and processing succeeds.

### Free-text extraction and the model adapter — criteria 2, 4, 6, 12 (A01)

All in [test_extraction.py](../tests/test_extraction.py). No test calls a hosted
model; live behavior is checked only by the demo script with a configured key.

- `test_free_text_intake_is_extracted_grounded_and_processed` — **1 case.** An
  intake without `changes` or `policy_number` is sent once to the fake; the grounded
  policy number and contact fields land on the case, `request_extracted`
  (actor `model:<name>`) and `proposal_validated` (`source: model_extraction`) are
  audited, and approval/execution apply exactly the extracted values.
- `test_structured_intake_never_calls_the_model` — **1 case.** Structured intake
  processes without any model call; `/health` names the configured provider.
- `test_unsupported_or_ambiguous_requests_pause_for_review` — **2 cases:** an
  unsupported request and an ambiguity each pause with their finding code and a
  follow-up draft quoting the item; a reviewer proposal edit resolves it without a
  second model call and without carrying the notes forward.
- `test_values_not_stated_in_the_text_are_dropped` — **4 cases:** a policy number
  inferred from a name, an email absent from the text, a phone with different
  digits, and an address with different wording are dropped, audited under
  `dropped`, and pause the case with `unverified_extraction`; the policy number
  stays unresolved (`missing_policy`).
- `test_injected_policy_number_cannot_escalate_access` — **1 case.** A policy number
  injected into the text survives grounding but still fails the broker assignment
  check: the case is `blocked` and cannot be approved.
- `test_model_failure_keeps_intake_retryable` — **1 case.** Queueing returns 202; the
  worker persists a retryable 503 or non-retryable 502 model error. The case stays
  `received` with no extraction event; a later retry succeeds.
- `test_known_policy_number_is_passed_as_context_not_reextracted` — **1 case.** A
  supplied policy number reaches the extraction context and cannot be replaced by the
  model response.
- `test_unconfigured_model_falls_back_to_structured_intake` — **1 case.** With
  `model=None`, `/health` reports `unconfigured` and free-text intake pauses with
  `missing_changes`.
- `test_gemini_client_sends_schema_and_keeps_the_key_out_of_the_url` — **1 case.**
  Through `httpx.MockTransport`: model path, `x-goog-api-key` header only, JSON
  response schema and system instruction in the body, parsed data and token usage.
- `test_gemini_client_maps_failures` — **5 cases:** 429 then 503 (retried once,
  retryable), 401 (single attempt, not retryable), empty candidates (retryable, not
  retried in-client), `MAX_TOKENS` finish (not retryable), and transport errors;
  error details never contain the key.
- `test_gemini_client_retries_once_then_succeeds` — **1 case.**
- `test_env_file_is_loaded_explicitly_without_overriding_the_shell` — **1 case.**
  Comments, `export`, quoted values with trailing comments, invalid names, and
  non-assignments are handled; shell variables win; only names are returned;
  `model_from_env` and the app factory (`POLICY_UPDATE_ENV_FILE`) build the client
  without a network call.

### Typed agent tools — criteria 2, 4, 5, 6, 7, 9, 12 (A02)

All in [test_tools.py](../tests/test_tools.py). Tools run through `run_tool` in a
service session (one transaction per call, like a worker step); reviewer approval
goes through the API because the tools cannot perform it.

- `test_registry_exposes_exactly_the_eight_permitted_tools` — schemas for exactly
  the eight plan responsibilities, strict objects, no reviewer operations, tokens,
  or workspace IDs in the contract.
- `test_get_policy_enforces_access_and_never_infers_the_number` — assigned policy is
  returned; an unassigned one fails without details; a number not stated in the
  text is refused and stays unresolved; a stated number binds as written; a
  mismatching number is refused.
- `test_check_broker_assignment_reports_without_policy_details`.
- `test_inspect_document_binds_only_evidence_of_this_case` — fixture and same-case
  upload bind; another case's attachment and a malformed ID are refused without
  changing the bound evidence.
- `test_validate_is_a_dry_run` — findings returned, no proposal created, unsupported
  fields rejected by the input contract.
- `test_agent_path_submits_waits_for_human_approval_then_applies` — inspect →
  submit (v1, awaiting approval) → apply refused (409) → human approves via API →
  apply → idempotent repeat → confirmation draft; completed case refuses further
  binding; `tool_called` events carry argument names only and `proposal_validated`
  is sourced `agent_tool`.
- `test_follow_up_pauses_the_case_and_a_reply_resumes_it` — clarification finding
  and draft, approval refused, a reply creates version 2 without the note.
- `test_unknown_tools_and_the_budget_stop_the_loop` — unknown tool and invalid
  arguments are structured errors; the third call over a budget of two raises
  `BudgetExhausted`; all attempts are audited.
- `test_tools_reuse_the_api_helpers` — structured processing and tool submission
  share the proposal shape.

### Agent loop — criteria 2, 3, 4, 6, 9, 10, 12 (A03–A05, A07)

All in [test_agent.py](../tests/test_agent.py), through the API with a `FakeChat`
that scripts the model's tool choices.

- `test_agent_selects_tools_waits_for_human_approval_and_applies` — four scripted
  tool choices lead to `awaiting_approval`; the prompt is checked (goal, eight tool
  declarations without `$ref`, request text marked as data, no policy values before
  `get_policy`, tool results fed back); `/resume` before approval is refused; after
  the reviewer approves, `/resume` lets the model apply version 1 and the case
  completes with a confirmation draft; `agent_decision`, `tool_called`,
  `processing_started`, and `agent_finished` events are recorded.
- `test_agent_asks_for_information_and_continues_after_a_reply` — `draft_follow_up`
  pauses the case (interrupt); a reply creates version 2; `/resume` shows the reply
  and the latest proposal to the model, which submits version 3.
- `test_model_that_stops_without_acting_pauses_for_a_human` — a final answer with no
  proposal produces `agent_stopped` plus the domain findings and quotes the model's
  sentence in the draft.
- `test_tool_budget_stops_the_loop_for_review` — `AGENT_TOOL_BUDGET=2`: two calls run,
  the third decision is never requested, the case pauses with the limit reason.
- `test_forbidden_or_unknown_tool_calls_are_observed_not_executed` — `approve_proposal`
  and a mismatching policy number come back as structured errors the model sees;
  nothing is approved or executable.
- `test_model_failure_keeps_the_case_processing_and_continues_from_checkpoint` — a
  retryable model error after step 1 fails the job (retryable, `processing_failed`)
  and leaves `processing`; `/resume` is refused with a `/retry` hint; `/retry`
  continues at step 2 without repeating step 1 and the job shows attempt 2. The
  saved error retains HTTP 503 instead of replacing it with a generic outage.
- `test_model_error_category_is_visible_without_provider_text` — **5 cases:**
  quota (429/RESOURCE_EXHAUSTED), authentication (401/UNAUTHENTICATED), read timeout,
  an unknown provider status, and arbitrary provider text. The job and failure
  audit retain only allowed diagnostic categories, preserve retryability, and
  expose no arbitrary provider text. No proposal is created.
- `test_interrupted_loop_survives_an_app_restart` — a new app instance over the same
  SQLite file resumes the interrupted thread after approval.
- `test_other_guests_cannot_process_or_resume_the_case` — 404 for another guest,
  401 without a token.
- `test_extraction_feeds_the_loop_without_creating_a_proposal` — free-text intake is
  extracted into `requested_changes`/`policy_number` and shown to the model with
  the extraction notes; only the model's tool creates version 1, and that first
  proposal still pauses on the extraction's unsupported item.
- `test_stalled_running_job_is_refused_until_retried` — a job left `running` with
  a lapsed lease makes `/process` answer 409 ("stalled; use /retry"); `/retry`
  queues and runs the attempt, and a later `/retry` after approval resumes and
  completes. The automatic sweep of the same situation is in test_worker.py.

### Adversarial runs — criteria 6, 9, 11, 12 (A08)

All in [test_adversarial.py](../tests/test_adversarial.py); the scripted model acts
as if steered by injected text.

- `test_steered_model_cannot_skip_evidence_approve_or_cross_policies` — apply before
  any proposal, a mismatching policy number, and a submission without evidence all
  fail as structured results; the case pauses, cannot be approved or executed, and
  the other policy's values never appear in the prompts.
- `test_instructions_inside_a_document_never_reach_the_model_or_the_case` — the
  instruction-bearing PDF is inspected to labeled fields only; its instruction text
  is absent from every prompt; approval is still required.
- `test_leaked_identifiers_and_forged_versions_are_useless_to_the_model` — another
  case's attachment ID, a forged version, an unsupported field, and a premature
  confirmation all fail without side effects.
- `test_agent_cannot_reach_another_workspace_even_with_its_case_id`.

### Job worker: claiming, leases, and stalled-job recovery — criteria 8, 10 (A05)

All in [test_worker.py](../tests/test_worker.py); agent-mode with `FakeChat`
unless noted.

- `test_exactly_one_worker_claims_a_queued_job` — two `Worker` objects over one
  database: the first claim wins, the second returns false and finds nothing to
  run; the running job shows the owner and a lease later than `started_at`;
  `/retry` is refused while the lease is live; the owner finishes it (`waiting`,
  lease cleared) and a non-owner's `finish_job` raises `LeaseLost`.
- `test_stalled_job_is_swept_back_to_the_queue_and_run_by_a_live_worker` — a
  `running` job whose lease lapsed (dead worker) is re-queued by the next worker
  pass (`processing_stalled` with the attempt number) and run to
  `awaiting_approval` as attempt 2 by the live worker.
- `test_job_that_keeps_stalling_fails_for_manual_retry` — a job that already
  stalled `MAX_JOB_ATTEMPTS` times is failed (retryable, explanatory
  `last_error`) instead of re-queued; `/retry` still queues and completes it.
- `test_worker_that_lost_its_lease_stops_before_acting_again` — a `FakeChat` hook
  hands the job to another worker mid-run: the first worker's next step raises
  `LeaseLost` before the second tool runs, records no decision, and leaves the
  job untouched; when the new owner's lease lapses too, the sweep re-queues it and
  the loop continues from the checkpoint (no repeated `get_policy`).
- `test_heartbeat_renews_the_lease_while_a_step_is_slow` — a one-second lease
  and a scripted decision that sleeps longer than it: the heartbeat thread has
  advanced `lease_expires_at`, a concurrent sweep finds nothing stalled, and the
  job finishes as attempt 1 under its original owner.
- `test_requeued_attempt_runs_what_the_case_needs_now` — a job left `running` after its
  run had fully committed is closed as `waiting` without a second proposal or a failure;
  a resume whose first model call failed (interrupt already consumed) is swept and
  _continued_ to completion rather than refused as "not waiting to be resumed".
- `test_embedded_worker_thread_runs_jobs_outside_the_request` —
  `worker_mode="embedded"`: `/process` returns a queued job and the background
  thread finishes it; approval plus `/resume` completes the case; shutdown joins
  the thread. The only test that runs a worker thread.
- `test_separate_worker_process_runs_queued_jobs` — rule-based (no key): a real
  `python -m policy_update.worker` subprocess over the same database claims and runs a
  queued job while the API only queues (`/health` reports `external`); the job's
  `worker_id` carries the subprocess PID; SIGTERM exits 0; the log excludes the request
  text and token. The database is initialized before the worker starts.
- `test_explicit_migration_adds_legacy_lease_columns` — drops
  `processing_jobs.lease_expires_at` from an unversioned legacy schema; startup refuses
  it until an explicit migration restores the column. Repeated revision verification
  leaves the upgraded schema intact.

### Persistence, concurrency, and failure recovery — criteria 8, 9, 10

`test_intake_is_persisted_before_processing` and
`test_processing_failure_keeps_intake_retryable` (test_workflow.py) also assert the
durable job record: `waiting` after a successful rule-based run, `failed`/retryable
with a `processing_failed` event after a simulated crash, and `attempts` counting
the retry.

- `test_paused_case_approval_and_receipt_survive_restart` — **1 case.** Recreates
  application instances against a temporary SQLite file at received, approved, and
  completed stages: the unprocessed intake is processed by a second instance, the
  token remains usable, and execution replay preserves the receipt/revision. This
  is app recreation, not a killed worker or PostgreSQL server restart;
  awaiting-information and LangGraph are not exercised. Killing the embedded
  worker thread mid-run is not simulated; the lapsed-lease tests above stand in
  for a dead worker.
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
`address`. Each test gets a fresh guest. SQLite uses a temporary file by default. New
test databases initialize through Alembic. An existing unversioned test database must be
explicitly migrated; deleting its records is not required. `TEST_DATABASE_URL` selects a
dedicated PostgreSQL database for the shared API suite; the explicit restart test always
uses SQLite. PostgreSQL tests leave synthetic rows, so never point this variable at
production/shared business data.

[fixtures.py](../src/policy_update/fixtures.py) provides four evidence dictionaries,
six sample requests, and seven sample documents in `src/policy_update/assets`
(regenerate with `scripts/make_evidence_assets.py`; the PDF writer is dependency-free
and the PNG uses Pillow, a dev dependency). `unreadable` sets both `readable` and
`certain` to false; the readable-but-uncertain case is covered by the
`missing-fields-pdf` document. Fixture source page 1 is metadata; attachment page
references come from actual `pypdf` text extraction. Neither establishes document
authenticity.

[scripts/demo.py](../scripts/demo.py) uses a running local server to exercise
contact-only, missing evidence/correction, and conflicting evidence/correction.
Each scenario submits intake, queues processing, polls the worker, approves through
the API, and checks duplicate execution. A fourth uploads a conflicting PDF, then
a corrected PDF bound by a reply. Two additional free-text scenarios run when a
model is configured.
The script drives reviewer actions; the configured backend may use the agent loop.
It is a manual smoke companion, separate from pytest and browser automation.
It creates synthetic records and performs simulated approvals/updates.

## Commands

Run from the repository root:

```sh
uv sync --locked
uv run pytest --collect-only -q
uv run pytest -q --tb=short
uv run pytest -q --tb=short -k 'intake or processing'
uv run pytest -q --tb=short tests/test_attachments.py
uv run pytest -q --tb=short tests/test_extraction.py
uv run pytest -q --tb=short tests/test_tools.py
uv run pytest -q --tb=short tests/test_agent.py
uv run pytest -q --tb=short tests/test_worker.py
uv run pytest -q --tb=short tests/test_adversarial.py
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
`uv run python scripts/demo.py` separately; with `GEMINI_API_KEY` configured every
`/process` is a live agent run. `uv run python scripts/evaluate_model.py` is the
labeled live evaluation (exit 0 when every example matches). Do not start a server or perform hosted
model calls for a documentation-only change, and never add a live model call to
the pytest suite.

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

For UI changes, follow [design-system.md](design-system.md), verify the user flow and
relevant screenshots, and record the viewport/state checked. The browser tooling is
described below.

## Coverage to add as implementation proceeds

### Existing backend gaps

- [ ] Broader normalization examples that must remain conflicting rather than match
  loosely; PDFs with multiple labeled names/addresses; JPEG uploads; encrypted PDFs;
  a `MAX_INSPECTED_PAGES` overflow.
- [ ] Explicit combined address/email/phone execution and contact-field boundary
  cases when those paths change; the suite does not enumerate every combination.
- [ ] Awaiting-information app restart and persisted replies/evidence history;
  reply with unchanged evidence and explicit evidence removal after approval.
- [ ] Concurrent `/process` calls on one received case (currently protected by the
  case row lock, case revision, and the unique proposal version, exercised only
  sequentially); processing after a mid-flight assignment change.
- [ ] Revocation before approval and after successful execution/replay; evidence
  snapshot changes before approval/execution; all terminal edit/reply paths.
- [ ] Controlled interleavings for competing edits/approvals/replies and different
  cases updating one policy; the existing different-case stale test is sequential.
- [ ] Additional relevant transaction failure windows and log-redaction assertions.
  Existing error-response checks do not prove all application logs are safe.

### Features not yet implemented

- [ ] E04 image path: OCR/model inspection of PNG/JPEG documents through the
  adapter; today images are only stored and reported uncertain.
- [ ] A01 follow-ups: extraction from reply text (replies currently reuse the
  previous proposal's changes), recording failed extraction attempts, and a
  separately labeled live evaluation of grounding on synthetic adversarial text
  (V09/A08). Grounding itself is covered above with fakes.
- [ ] A05 follow-ups: a worker killed mid-step is simulated by a lapsed lease, not
  by killing a process; two worker processes racing on one queue are exercised as
  two `Worker` objects in one process (same compare-and-set) in the suite — a
  manual 20-job race between two real processes on PostgreSQL ran clean
  (2026-09-12) but is not a test. The sweeper-versus-owner lock order is proved
  by a manual PostgreSQL probe, not by the suite (SQLite has no row locks). The live evaluation covers seven texts on one model; a broader corpus
  or other providers are not measured.
- [ ] U07 follow-ups: actual Safari/VoiceOver and wider transient-state and large-queue
      checks. Three-engine, contrast, and slow-submission checks are recorded below.
      Live Gemini flows were checked manually.
- [ ] V08: actual hosting configuration, scheduled cleanup, host restart, and hosted
      smoke checks.
- [ ] V09: separately measured synthetic model extraction and end-to-end outcomes.

These gaps are not a request to write speculative tests before their feature
exists. Add coverage alongside the behavior or when a concrete risk is investigated.

## Dashboard browser coverage — U01–U07

[dashboard.spec.ts](../frontend/tests/dashboard.spec.ts) contains **11 scenarios per
engine, 33 checks across Chromium, Firefox, and WebKit**:

1. Guest entry, contact intake, comparison, separate approval/application, confirmation
   draft, persisted activity, and reload.
2. Delayed intake disables duplicate submission, retains the modal, and saves one case.
3. An invalid guest cookie clears the previous case selection and allows a fresh
   workspace.
4. Missing evidence blocks approval; a corrected PDF/reply creates version 2.
5. Conflicting evidence follows the same correction path.
6. Editing invalidates approval; a stale dialog submission fails and retains input.
7. Rejection records its reason and removes approval actions.
8. HttpOnly/Strict cookies, separate guest contexts, cross-workspace 404, and
   cross-origin write rejection through the proxy.
9. Unassigned broker access shows no current policy contact values or approval controls.
10. Narrow viewport, keyboard tabs, dialog Escape/focus restoration, and a mocked
    approval outage that remains an error.
11. A scripted extraction 429 is persisted, shown safely, and retried to a proposal.

The capture helper runs axe WCAG A/AA checks on saved states and the delayed-intake
modal in each engine. Screenshot files are generated only when requested, in Chromium;
they are reviewed references, not pixel-comparison assertions.

[serve_backend.py](../frontend/tests/serve_backend.py) starts a fresh temporary SQLite
API with a scripted extraction fake, no agent model, and an embedded worker. Unexpected
free-text inputs fail. Playwright uses ports **8001/3001**, refuses to reuse existing
servers, and creates isolated browser contexts. It does not load `.env`, call Gemini, or
use `policy_demo.db`.

From the repository root, then inside `frontend`:

```sh
uv sync --locked
cd frontend
npm ci
npx playwright install chromium firefox webkit
npm run format:check
npm run typecheck
npm run build
npm test
```

Optional: to generate 14 synthetic reference images in `_docs/screenshots/`, run
`CAPTURE_BASELINE=1 npm test -- --project=chromium` after a build. Review the images
for visual QA; saved images are not required by tests. State/viewport details live in
[design-system.md](design-system.md).

## Operational coverage — V05–V07

[test_operations.py](../tests/test_operations.py) covers:

- Legacy migration retains completed receipts, proposal/audit history, and idempotent
  replay; the resulting schema matches application metadata.
- Revision 0001 → 0002 retains attachment bytes and backfills usage counters.
- Expiry denies API access and queued processing; cleanup preserves other guests.
- Case/file/run limits reject excess operations without consuming rejected budgets.
- Independent sessions cannot reserve the same final quota unit.
- Oversized request bodies are refused before multipart parsing.
- Verify mode refuses an unmigrated database.
- Cleanup deletes real LangGraph checkpoint threads and private attachment bytes.
- A global queue limit rolls back the new job and workspace budget reservation.

With `TEST_DATABASE_URL`, migration/cleanup retention tests create their own schema and
drop only that schema at teardown. Other PostgreSQL tests create synthetic guests. Use a
dedicated UTF-8 test database; never use a shared business database.

[scripts/smoke_containers.py](../scripts/smoke_containers.py) separately checks the
model-free Compose stack: private proxy, separate worker, explicit approval, receipt
replay, persisted waiting case, PDF correction, and cross-guest case/file denial.
`--restart` also restarts PostgreSQL, API, worker, and frontend. Follow the
[runbook](deployment.md#local-container-verification) for the matching project name.

## Manual and hosted evidence

The owner reported three local Gemini/dashboard scenarios passing on 2026-09-13: valid
approval/application, missing evidence corrected on the same case, and conflicting
evidence corrected on the same case. Case IDs, timings, and recordings were not
retained. This is separate from automated checks with scripted models. The earlier
seven-request synthetic Gemini evaluation is recorded under A08 in
[process.md](process.md); it does not measure broad accuracy or attack resistance.

Remaining U07 checks: actual Safari, keyboard-only navigation at 200% zoom, and
VoiceOver. Verify queue/status announcements, tabs, table headers, dialog titles, focus,
and validation/retry errors; complete evidence correction and approval without a mouse.
Record browser/macOS versions and findings. Axe and Playwright WebKit do not establish
screen-reader or Safari application coverage.

Hosted CI, deployment/restart acceptance, model latency/cost measurements, and demo
recordings remain pending. Add actual results to the delivery checklist when run.
