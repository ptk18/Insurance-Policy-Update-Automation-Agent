# Work process and delivery checklist

Last compared with the working tree: 2026-09-12.

## Sources and status rules

[plan.md](plan.md) defines scope and acceptance criteria. This file tracks delivery;
[testing-guidelines.md](testing-guidelines.md) records coverage;
[design-system.md](design-system.md) records UI decisions and gaps.

`[x]` means the specifically named task is implemented in the current code.
`[ ]` means work remains. A task labeled **Partial** names both the existing piece
and the missing piece. Backend or fixture completion is not completion of a full
agent/dashboard acceptance criterion. A configured CI workflow is not evidence
that hosted CI has run. Do not derive a completion percentage from checkbox counts.

## How to work

1. Read the scope and pick a bounded task below. Follow dependencies; prioritize
   the core demo before later phases. Keep task IDs stable when splitting work.
2. Inspect the relevant code and existing tests. For UI work, read the design
   baseline before choosing components, states, or visual values.
3. Implement the behavior through the existing backend controls. Keep synthetic
   shortcuts explicit and preserve authorization, versioning, and atomic updates.
4. Run checks appropriate to the change using the testing guide. Record actual
   results and limitations; documentation-only work needs reference checks.
5. Update this checklist and the relevant coverage/design records in the same
   change. Mark only verified implementation done and cite the supporting code.
6. Hand off what changed, verification performed, and the next unfinished task.
   Follow [AGENTS.md](../AGENTS.md) and the user's permissions for external actions.

For a task to be done, its named behavior must exist, relevant checks must pass,
and documentation must describe its actual limits. Do not close an agent task
using the fixture API or close a UI task using Swagger screenshots.

## 1. Backend foundation

Evidence: [API](../src/policy_update/api.py),
[service](../src/policy_update/service.py),
[schemas](../src/policy_update/schemas.py),
[models](../src/policy_update/models.py), and
[validation](../src/policy_update/validation.py).

- [x] B01 — Scaffold Python, FastAPI, Pydantic, SQLAlchemy, dependency lock, and
  local setup commands.
- [x] B02 — Create guest workspaces with hashed bearer tokens and isolated seeded
  policies and simulated broker assignments.
- [x] B03 — Accept structured case input with original email text, explicit policy
  number, fixed simulated broker, and proposed contact changes.
- [x] B04 — Limit changes to mailing address, email, and phone; reject unsupported
  fields and validate contact formats.
- [x] B05 — Pause missing/unknown policy numbers with clarification drafts; enforce
  broker assignment on direct API/domain operations, including revoked access.
- [x] B06 — Compare fixture name/address evidence, allow formatting differences,
  and block the whole request for missing, conflicting, or unreadable evidence.
- [x] B07 — Add replies and replacement fixture evidence to the same case and
  revalidate; generate template clarification drafts.
- [x] B08 — Version proposals and preserve before/after values, findings, evidence
  snapshots, and historical approval records. Edits/replies supersede old versions.
- [x] B09 — Approve/reject through reviewer API operations; bind approval to the
  current version and recheck policy revision, evidence, and authorization.
- [x] B10 — Persist simulated policy updates, unique execution receipts, audit
  outcomes, and case completion transactionally. Return saved receipts on retry.
- [x] B11 — Return case list/detail, audit timeline, and template confirmation drafts
  through the API. No outbound email.
- [x] B12 — Support persistent SQLite and PostgreSQL storage with row locking and
  optimistic revisions. Bootstrap missing tables without resetting records.
- [x] B13 — Separate intake persistence from processing. `POST /cases` only
  persists the case (`received`, optional `requested_changes`); `POST
  /cases/{id}/process` runs `service.process_case` in its own transaction and is
  refused once a case has left `received`. Version-bound actions on an unprocessed
  case fail with 409. Since A05 the route only queues a durable job (`202`) that
  the worker runs.

## 2. Attachments and evidence

Evidence sources: [fixtures.py](../src/policy_update/fixtures.py) (named fixture
dictionaries; their page 1 reference is metadata, not extraction) and uploaded
attachments inspected by [documents.py](../src/policy_update/documents.py).

- [x] E01 — Seed example requests and matching/conflicting/wrong-name/unreadable
  evidence dictionaries for backend scenarios.
- [x] E02 — Seven synthetic PDF/PNG assets in `src/policy_update/assets` (generated
  by `scripts/make_evidence_assets.py`), listed with size/type/expected outcome by
  `GET /fixtures` and served by `GET /fixtures/documents/{id}`. Storage choice:
  attachment bytes are stored in the `attachments` table (deferred column) scoped by
  workspace and case; object storage is a later swap of that column only.
- [x] E03 — `POST /cases/{id}/attachments` (multipart, type sniffed from bytes: PDF,
  PNG, JPEG; `MAX_ATTACHMENT_BYTES`, default 5 MiB; sanitized filename; editable
  cases only) and authorized `GET .../attachments/{id}` and `.../content`. Other
  workspaces get 404; content responses are `private, no-store`.
- [ ] E04 — **Partial:** PDF text layers are inspected deterministically for labeled
  `Account holder`/`Service address` lines with page references, unreadable and
  uncertain reasons, and no effect from other document text. Image documents are
  stored and validated but inspection reports them uncertain; image/OCR inspection
  through the model adapter is deferred (A01 shipped text-only).
- [x] E05 — `evidence_id` on intake replies accepts a fixture name or a same-case
  attachment ID; an upload to a `received` case binds automatically, later uploads
  bind through a reply, which creates a new version and invalidates approval. Every
  proposal keeps its own evidence snapshot with the attachment reference.
- [x] E06 — [test_attachments.py](../tests/test_attachments.py) covers matching,
  conflicting, wrong-name, scanned, missing-field, image, and instruction-bearing
  documents, corrected uploads, type/size/state rejection, cross-workspace and
  cross-case isolation, and restart. Image inspection and real OCR/model extraction
  are not proven; document authenticity is not checked.

## 3. Bounded agent and durable processing

The bounded loop in [agent.py](../src/policy_update/agent.py) runs when a model
is configured (`GEMINI_API_KEY`; `AGENT_LOOP=off` keeps rule-based processing).
`POST /cases/{id}/process`, `/resume`, and `/retry` queue a durable job and answer
`202`; the worker in [worker.py](../src/policy_update/worker.py) claims it, moves
the case to `processing`, extracts free text if needed, and runs the LangGraph loop
(or rule-based processing when no model is configured) outside any request.

- [x] A01 — Provider: Gemini (`gemini-3.8-flash` by default, `GEMINI_MODEL`
  override) through `generateContent` REST with a JSON response schema;
  `GEMINI_API_KEY` is loaded explicitly from `.env` by
  [settings.py](../src/policy_update/settings.py). Free-text intake (no `changes`)
  is extracted by [extraction.py](../src/policy_update/extraction.py) and grounded:
  values not verbatim in the text are dropped (`unverified_extraction`), the policy
  number is never inferred from a name, and unsupported/ambiguous wording pauses the
  case (`unsupported_request`/`ambiguous_request`). Model failures return 503/502
  and leave the case `received`. Text only: image document inspection through the
  model is deferred (E04 stays partial). Verified live on synthetic text
  (2026-09-12); the test suite uses scripted fakes and a mocked transport.
- [x] A02 — [tools.py](../src/policy_update/tools.py) registers exactly the eight
  plan responsibilities (`get_policy`, `check_broker_assignment`,
  `inspect_document`, `validate_proposed_changes`, `draft_follow_up`,
  `submit_for_approval`, `apply_approved_update`, `draft_confirmation`) with strict
  Pydantic inputs, JSON schemas for the model, and structured error results. Tools
  run against one already-authorized case in the caller's transaction and delegate
  to the service layer, so authorization, permitted fields, evidence, versioning,
  and idempotent execution are unchanged; `get_policy` binds a missing number only
  when it is stated verbatim in the request. Approve/reject/edit and the reviewer
  token are not reachable. `run_tool` enforces a call budget (`BudgetExhausted`) and
  audits every call as `tool_called` (tool, argument names, outcome). No loop calls
  them yet (A03).
- [x] A03 — LangGraph `StateGraph` (`decide → act → wait | finish`): each turn the
  model receives the goal, the eight tool declarations, the prior tool results, and
  a case snapshot with request text marked as data, and answers with one Gemini
  function call or a final sentence. `act` runs the tool in its own transaction.
  The per-segment budget (`AGENT_TOOL_BUDGET`, default 12) and a model that stops
  without leaving a proposal both pause the case for review with an
  `agent_stopped` finding. Verified live: contact-only, fixture-evidence, uploaded
  PDF, and free-text cases resolved through model-chosen tool sequences
  (2026-09-12, `gemini-3.5-flash-lite` after `gemini-3.8-flash` hit free-tier
  quota); the suite uses a scripted `FakeChat`.
- [x] A04 — A tool call that moves the case into `awaiting_information` or
  `awaiting_approval` raises a LangGraph `interrupt`; `/resume` continues only an
  `awaiting_information` case (after a reply) or an `approved` case, refusing an
  unapproved one. Approve/reject/edit remain reviewer API actions; the loop never
  sees a bearer token and observes approval only through case state.
- [x] A05 — Checkpoints persist in LangGraph's tables in the same SQLite file or
  PostgreSQL database (`make_checkpointer`), keyed by case ID, so an interrupted or
  failed loop survives a restart and continues from its last completed step. The
  loop runs outside API requests: the routes only queue a job (`202`), and the
  worker claims it with a compare-and-set update (`queued → running` under its
  worker ID and a lease, `JOB_LEASE_SECONDS`), renews the lease from a heartbeat
  thread, and re-checks ownership inside every processing step's transaction so a
  worker paused past its lease stops instead of acting on a case another worker
  took over (`LeaseLost`). Any worker's poll sweeps lapsed leases back into the
  queue (`processing_stalled`) and fails a job that stalled `MAX_JOB_ATTEMPTS`
  times for a manual `/retry`. `WORKER_MODE=embedded` (default) runs the worker
  as a thread in the API process; `external` leaves the work to
  `python -m policy_update.worker` processes over the same database. Proved by
  [test_worker.py](../tests/test_worker.py) on SQLite and PostgreSQL (exclusive
  claim, sweep and rerun, poison cap, lease fencing with checkpoint continuation,
  embedded thread, a real separate worker process) and by the demo in both modes
  (2026-09-12, rule-based, no model key). A killed worker host was not exercised
  live; the stalled-job path is simulated by a lapsed lease.
- [x] A06 — Every `/process`, `/resume`, and `/retry` attempt is a durable
  `ProcessingJob` row (action, `queued|running|waiting|completed|failed`, attempts,
  `retryable`, sanitized `last_error`, `worker_id`, `lease_expires_at`), committed
  at queue time, claim time, and after the run, so a model failure (outage
  retryable, other errors not), a crash inside the worker, or a dead worker leaves
  a visible record and a `processing_failed`/`processing_stalled` audit event while
  the case keeps its last committed state (`received`, or `processing` with its
  checkpoint). `POST /cases/{id}/retry` queues whichever attempt applies and is the
  only manual way past a stalled `running` job before the sweep reclaims it;
  `/process` and `/resume` refuse a queued or live-leased job and mismatched
  states with a hint. Execution retry remains the idempotent `/execute`. The case
  view carries `job`, the list `job_status`. The Gemini client retries once
  honouring `Retry-After`. Agent and extraction failures retain the HTTP code and
  allowlisted Google status/transport category in `job.last_error` and the failure
  audit, without exposing arbitrary provider text (reporting fix, 2026-09-12).
- [x] A07 — The timeline records `processing_queued`, `processing_started`,
  `request_extracted`, per-turn `agent_decision` (chosen tool and the model's
  one-sentence stated intent, capped at 300 characters), per-call `tool_called`
  (tool, argument names, outcome), `agent_finished`, and the job outcomes
  (`processing_finished`, `processing_failed`, `processing_stalled`). Hidden
  reasoning, raw request text, and document contents are never recorded.
- [x] A08 — Deterministic fakes cover tool boundaries and budget
  ([test_tools.py](../tests/test_tools.py)), model errors, interruption/resumption,
  crash continuation, and restart ([test_agent.py](../tests/test_agent.py)), and a
  model steered by injected request/document text
  ([test_adversarial.py](../tests/test_adversarial.py): skipping evidence, forged
  versions, cross-policy and cross-workspace access, leaked attachment IDs,
  unsupported fields, instruction-bearing PDFs). The separate live evaluation
  [scripts/evaluate_model.py](../scripts/evaluate_model.py) runs seven synthetic
  and adversarial texts through the API and checks backend invariants; it is a
  labeled synthetic measurement, not an accuracy or security claim. Run 2026-09-12
  on `gemini-3.5-flash-lite`: 7/7 after two fixes it surfaced (extraction notes now
  pause the first agent proposal; a structurally supplied policy number is passed
  as context and never re-extracted).

## 4. Review dashboard

Depends on the [design baseline](design-system.md). The existing API supports early
UI integration. The Next.js dashboard, shared styles, and screenshot baseline now
live in `frontend/` and `_docs/screenshots/`. The browser suite uses an isolated
SQLite API, rule-based processing, and one scripted extraction retry; live-agent
browser verification and broader accessibility checks remain pending.

- [x] U01 — Establish visual tokens, component/state conventions, and responsive
  layouts; record the first implemented baseline and screenshot references.
- [x] U02 — Scaffold Next.js/React, guest session entry, sample selection, pasted
  email intake, and attachment upload against the backend.
- [x] U03 — Build case list/detail with status, original request/replies, supporting
  documents and sources, validation findings, and current/proposed values.
- [x] U04 — Implement editing, explicit version-bound approve/reject controls,
  stale-version refresh, and approval invalidation feedback.
- [x] U05 — Implement missing-information/corrected-evidence flow on the same case,
  visible draft follow-ups, and backend-supported processing resume.
- [x] U06 — Show approved-but-unapplied state, execution progress/failure, manual
  retry, persisted outcome, confirmation draft, and audit timeline.
- [ ] U07 — **Partial:** Chromium checks cover keyboard tabs, dialog focus/escape,
  status/error feedback, guest isolation, core review/correction/retry flows, and
  a 390 px layout; reference screenshots are saved for the core persistent states.
  Screen-reader/contrast audit, other browsers, transient-state baselines, and
  automated visual comparisons remain. See the design and testing records.

## 5. Verification and deployment

Evidence: [tests](../tests/test_workflow.py),
[CI configuration](../.github/workflows/ci.yml), and
[demo script](../scripts/demo.py).

- [x] V01 — Add backend regression tests: 74 test functions / 97 parameterized
  cases across seven modules. See the testing guide for assertions, run history,
  and gaps; the latest model-error reporting checks use fakes, not a live API.
- [x] V02 — Verify the backend suite locally on SQLite and PostgreSQL; verify lint
  and formatting. A06/A08 session (2026-09-12): 83 passed on SQLite and on a dedicated
  local PostgreSQL test database; `ruff check`/`ruff format --check` clean.
- [x] V03 — Configure CI to run lint/format and tests on SQLite/PostgreSQL 17.
  Hosted CI execution is not yet verified.
- [x] V04 — Run a local API smoke script for contact-only, missing evidence/resume,
  conflict/correction, uploaded-PDF conflict/correction, and (with a configured
  key) live free-text extraction and unsupported-change pause scenarios, with
  duplicate execution checks on the fixture scenarios. In agent mode the script
  prints the model-chosen tool sequence, retries `/process` on 502/503, and calls
  `/resume` after approval (rerun 2026-09-12: five of six scenarios completed on
  `gemini-3.5-flash-lite`; the sixth hit the free-tier per-minute quota).
- [ ] V05 — Add versioned migrations and verify upgrades with retained demo data.
- [ ] V06 — Add guest expiry/cleanup, resource limits, private storage configuration,
  and safe operational logging appropriate to the public demo.
- [ ] V07 — Add Docker and managed-host configuration for frontend, API, worker,
  PostgreSQL, and private attachments. Confirm provider choices from the plan.
- [ ] V08 — Deploy within user-authorized scope; verify hosted CI, all acceptance
  criteria, cross-guest isolation, restart recovery, and execution retry.
- [ ] V09 — Record the three requested demo-video scenarios with the actual agent
  and dashboard. Measure synthetic results and label method/sample size; make no
  unsupported accuracy, time-saving, or production-readiness claims.

## Acceptance criteria: current evidence and remaining proof

Numbers refer to the twelve criteria in [plan.md](plan.md). These are readiness
notes, not an assertion that the full deployed product passes acceptance.

1. **Partial:** isolated guests and samples via API (B02/E01); guest entry/sample intake and browser isolation verified locally (U02). Hosted proof remains.
2. **Partial:** fixture- and PDF-backed proposals, grounded free-text extraction,
   and model-selected tool sequences work (B06/B08/E04/A01–A04); image inspection
   through the model is absent.
3. **Agent covered:** contact-only proceeds without attachment through the loop
   (B04/B09/A03/V01/V04); local browser review/approval/application verified with the rule-based worker (U02–U04); live agent UI proof remains.
4. **Agent covered:** missing number/evidence, scanned, and unlabeled PDFs pause
   and draft clarification, and the loop's `draft_follow_up` pauses via interrupt
   (B05/B06/E04/A04).
5. **Backend covered:** conflicting fixtures and PDFs block; a corrected reply or
   corrected upload bound by a reply creates a valid new version (B07/B08/E05);
   the dashboard correction flow is verified with matching uploaded PDFs (U05).
6. **API and agent covered:** unassigned/revoked access and cross-workspace
   attachment access are denied (B05/E03/V01); the typed tools reuse those checks,
   cannot reach approval, and the loop refuses other guests (A02–A04); adversarial
   model evaluation remains (A08).
7. **Partial:** before/after data and exact-version approval exist (B08/B09);
   the reviewer dashboard exposes the values and version-bound actions (U03/U04). Hosted acceptance remains.
8. **Partial:** execution, saved values/audit, and confirmation template exist
   (B10/B11); the dashboard shows the persisted applied values, activity, and unsent confirmation (U06). Live-agent browser verification remains.
9. **API and agent covered:** unapproved/stale execution is rejected and the loop's
   `apply_approved_update` fails before approval (B09/B10/A04/V01); the browser checks approval invalidation and stale edits (U04).
10. **Backend covered:** app recreation retains cases, receipts, job records, and
    the interrupted LangGraph thread, which resumes after restart; a failed step
    continues from its checkpoint; a job whose worker stopped renewing its lease is
    swept back to the queue and finished by a live worker, or fails visibly after
    `MAX_JOB_ATTEMPTS` (A05/A06). Host restart in the deployed environment remains
    (V08).
11. **Cases/policies/attachments covered:** API tenant isolation exists
    (B02/E03/V01); browser session separation is verified with independent cookie contexts (U02).
12. **Covered for the backend:** raw request text, forged approval input,
    instruction text inside an uploaded PDF, and a model steered by any of them
    cannot bypass evidence, approval, authorization, or isolation (E06/A01/A08);
    the live synthetic evaluation passed 7/7 on one model. No claim is made about
    other models or a broader attack corpus.

## Later phases

- [ ] L01 — After deployed core acceptance, add case chat grounded in stored case
  records, draft rewriting, preview/confirmation for edits, and permitted resume.
  Chat must not grant approval or bypass validation/versioning.
- [ ] L02 — Later, design a real inbox adapter, sender authentication, thread
  matching, access configuration, and outbound-message policy with separate tests.
  Real sending is outside the initial demo.

Next work: complete broader dashboard verification (U07) and a live-agent browser
walkthrough, then migrations and deployment readiness (V05–V08). Image inspection
(E04) remains explicitly deferred; the dashboard currently supports text PDFs.
