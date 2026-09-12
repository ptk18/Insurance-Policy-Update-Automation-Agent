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
  case fail with 409. Processing is still a synchronous rule-based stand-in for the
  planned worker: no job record, queue, or LangGraph checkpoint exists (A05/A06).

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

B13 and E02–E05 are in place, so both the contact-only and PDF address paths
attach to `process_case`; A01 adds model extraction for free-text intake. No
LangGraph dependency or agent worker exists in the current tree.

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
- [ ] A02 — Expose typed, case/workspace-scoped tools for all eight responsibilities
  in the plan. **Partial:** domain validation, authorization, proposals, execution,
  and drafts exist; model-facing tool contracts and registration do not.
- [ ] A03 — Implement genuine LLM tool selection and observation through LangGraph.
  Enforce a bounded tool-call budget and stop for review on ambiguity/exhaustion.
- [ ] A04 — Interrupt for information and human approval, resume eligible cases,
  and exclude approval operations/reviewer credentials from model access.
- [ ] A05 — Persist LangGraph checkpoints and processing jobs independently of the
  browser request, including recovery after a worker restart.
- [ ] A06 — Persist temporary failures and expose manual processing/execution retry.
  **Partial:** execution retries already preserve approval and idempotency, a
  failed or model-unavailable `/process` request leaves the intake `received` so it
  can be resubmitted, and the Gemini client retries once (honouring `Retry-After`);
  there is no worker retry API or durable failed/retryable job state, and a failed
  extraction attempt is not recorded.
- [ ] A07 — Record tool calls, outcomes, and concise decision summaries. **Partial:**
  domain audit events and the `request_extracted` event (grounded fields, dropped
  values, token usage) exist; model tool execution history does not.
- [ ] A08 — Test tool boundaries, malicious email/document instructions, model
  errors, interruption/resumption, and budget exhaustion with deterministic fakes;
  separately evaluate authorized hosted-model runs on synthetic examples.

## 4. Review dashboard

Depends on the [design baseline](design-system.md). The existing API supports early
UI integration, but no Next.js app, components, styles, or screenshots exist yet.

- [ ] U01 — Establish visual tokens, component/state conventions, and responsive
  layouts; record the first implemented baseline and screenshot references.
- [ ] U02 — Scaffold Next.js/React, guest session entry, sample selection, pasted
  email intake, and attachment upload against the backend.
- [ ] U03 — Build case list/detail with status, original request/replies, supporting
  documents and sources, validation findings, and current/proposed values.
- [ ] U04 — Implement editing, explicit version-bound approve/reject controls,
  stale-version refresh, and approval invalidation feedback.
- [ ] U05 — Implement missing-information/corrected-evidence flow on the same case,
  visible draft follow-ups, and backend-supported processing resume.
- [ ] U06 — Show approved-but-unapplied state, execution progress/failure, manual
  retry, persisted outcome, confirmation draft, and audit timeline.
- [ ] U07 — Verify keyboard use, focus, readable status/error feedback, loading and
  empty states, narrow layouts, and visual consistency across all core scenarios.

## 5. Verification and deployment

Evidence: [tests](../tests/test_workflow.py),
[CI configuration](../.github/workflows/ci.yml), and
[demo script](../scripts/demo.py).

- [x] V01 — Add backend regression tests: 40 test functions / 59 parameterized
  cases across three modules. See the testing guide for assertions and gaps.
- [x] V02 — Verify the backend suite locally on SQLite and PostgreSQL; verify lint
  and formatting. A01 session (2026-09-12): 59 passed on SQLite and on a dedicated
  local PostgreSQL test database; `ruff check`/`ruff format --check` clean.
- [x] V03 — Configure CI to run lint/format and tests on SQLite/PostgreSQL 17.
  Hosted CI execution is not yet verified.
- [x] V04 — Run a local API smoke script for contact-only, missing evidence/resume,
  conflict/correction, uploaded-PDF conflict/correction, and (with a configured
  key) live free-text extraction and unsupported-change pause scenarios, with
  duplicate execution checks on the fixture scenarios (rerun 2026-09-12 against
  Gemini).
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

1. **Partial:** isolated guests and samples via API (B02/E01); guest UI absent (U02).
2. **Partial:** fixture- and PDF-backed proposals work and free-text requests are
   extracted with grounding (B06/B08/E04/A01); model tool selection and image
   inspection are absent (A02–A04).
3. **Backend covered:** contact-only proceeds without attachment (B04/B09/V01);
   demonstrate it through the agent and UI (A03/U02–U04).
4. **Backend covered:** missing number/evidence, scanned, and unlabeled PDFs pause
   and draft clarification (B05/B06/E04); agent-driven follow-up remains (A02).
5. **Backend covered:** conflicting fixtures and PDFs block; a corrected reply or
   corrected upload bound by a reply creates a valid new version (B07/B08/E05);
   the dashboard flow remains (U05).
6. **API covered:** unassigned/revoked access and cross-workspace attachment access
   are denied (B05/E03/V01); prove future agent tools preserve the boundary (A02/A08).
7. **Partial:** before/after data and exact-version approval exist (B08/B09);
   reviewer dashboard absent (U03/U04).
8. **Partial:** execution, saved values/audit, and confirmation template exist
   (B10/B11); model execution and dashboard presentation absent (A02/U06).
9. **API covered:** unapproved/stale execution is rejected (B09/B10/V01);
   verify through agent and UI integrations (A08/U04).
10. **Partial:** app recreation over SQLite retains received/awaiting-approval/
    approved cases and receipts, and duplicate execution is covered. Awaiting-
    information restart, LangGraph checkpoints, and worker/host restart recovery
    remain (A05/V08).
11. **Cases/policies/attachments covered:** API tenant isolation exists
    (B02/E03/V01); browser session separation remains (U02).
12. **Partial:** raw request text, forged approval input, and instruction text
    inside an uploaded PDF cannot bypass the current API (E06); extracted values
    are limited to text that is actually present and still pass authorization
    (A01). No adversarial evaluation of the hosted model itself exists (A08).

## Later phases

- [ ] L01 — After deployed core acceptance, add case chat grounded in stored case
  records, draft rewriting, preview/confirmation for edits, and permitted resume.
  Chat must not grant approval or bypass validation/versioning.
- [ ] L02 — Later, design a real inbox adapter, sender authentication, thread
  matching, access configuration, and outbound-message policy with separate tests.
  Real sending is outside the initial demo.

Next work: A02–A05 (typed tools, LangGraph loop, interrupts, durable jobs) and
the deferred image inspection through the adapter (E04), which attach to
`process_case` and the stored attachments without changing intake. UI work can proceed against existing
endpoints once U01 establishes its baseline.
