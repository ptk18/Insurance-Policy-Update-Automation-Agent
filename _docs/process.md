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
- [ ] B13 — Separate intake persistence from processing. **Partial:** domain
  functions exist, but `create_case` immediately invokes `prepare_proposal` in the
  HTTP transaction and `Intake` still requires caller-supplied `changes`.

## 2. Attachments and evidence

Current evidence source: [fixtures.py](../src/policy_update/fixtures.py).
Fixture IDs and page 1 references do not represent uploaded files or extraction.

- [x] E01 — Seed example requests and matching/conflicting/wrong-name/unreadable
  evidence dictionaries for backend scenarios.
- [ ] E02 — Create fictional PDF/image proof-of-address assets and sample download
  metadata. Select private storage and persist attachment ownership by case/guest.
- [ ] E03 — Add PDF/image upload and authorized retrieval, file validation, size
  limits, and attachment isolation. Prevent access by another workspace.
- [ ] E04 — Implement document inspection with extracted name/address, uncertainty,
  and source references to actual documents/pages. Treat contents as untrusted.
- [ ] E05 — Connect extracted evidence to validation, same-case corrected uploads,
  and version invalidation. Preserve earlier evidence references for review.
- [ ] E06 — Test actual missing/unreadable/conflicting/corrected documents and
  unauthorized attachment access; do not reuse fixture success as extraction proof.

## 3. Bounded agent and durable processing

Depends on B13; contact-only tool-loop work can start while attachments are built.
The full address path depends on E02–E05. No LangGraph/model dependencies or agent
worker exist in the current tree.

- [ ] A01 — Select one hosted model/provider and implement its adapter, structured
  request extraction, and handling of unsupported or ambiguous English requests.
  Missing policy numbers must remain unresolved, never inferred from identity.
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
  **Partial:** execution retries already preserve approval and idempotency; there
  is no worker retry API or durable failed/retryable job state.
- [ ] A07 — Record tool calls, outcomes, and concise decision summaries. **Partial:**
  domain audit events exist; model tool execution history does not.
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

- [x] V01 — Add backend regression tests: 19 test functions / 26 parameterized
  cases. See the testing guide for exact assertions and uncovered branches.
- [x] V02 — Verify the backend suite locally on SQLite and PostgreSQL; verify lint
  and formatting. Prior build session: 26 passed on each database.
- [x] V03 — Configure CI to run lint/format and tests on SQLite/PostgreSQL 17.
  Hosted CI execution is not yet verified.
- [x] V04 — Run a local API smoke script for contact-only, missing evidence/resume,
  and conflict/correction scenarios, each with duplicate execution checks.
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
2. **Partial:** fixture-backed proposals work (B06/B08); model tool selection and
   actual document evidence absent (E04/A01–A04).
3. **Backend covered:** contact-only proceeds without attachment (B04/B09/V01);
   demonstrate it through the agent and UI (A03/U02–U04).
4. **Backend covered with fixtures:** missing number/evidence pauses and drafts
   clarification (B05/B06); extraction and agent-driven follow-up remain (E04/A02).
5. **Backend covered with fixtures:** conflict blocks and a corrected reply creates
   a valid new version (B07/B08); uploaded correction/resume remains (E05/U05).
6. **API covered:** unassigned/revoked access is denied (B05/V01); prove future
   agent tools and attachment paths preserve the boundary (E03/A02/A08).
7. **Partial:** before/after data and exact-version approval exist (B08/B09);
   reviewer dashboard absent (U03/U04).
8. **Partial:** execution, saved values/audit, and confirmation template exist
   (B10/B11); model execution and dashboard presentation absent (A02/U06).
9. **API covered:** unapproved/stale execution is rejected (B09/B10/V01);
   verify through agent and UI integrations (A08/U04).
10. **Partial:** app recreation over SQLite retains awaiting-approval/approved cases
    and receipts, and duplicate execution is covered. Awaiting-information restart,
    LangGraph checkpoints, and worker/host restart recovery remain (A05/V08).
11. **Cases/policies covered:** API tenant isolation exists (B02/V01);
    attachment isolation and browser session separation remain (E03/E06/U02).
12. **Partial:** raw request text and forged approval input cannot bypass the
    current API. No LLM or uploaded-document injection evaluation exists (A08/E06).

## Later phases

- [ ] L01 — After deployed core acceptance, add case chat grounded in stored case
  records, draft rewriting, preview/confirmation for edits, and permitted resume.
  Chat must not grant approval or bypass validation/versioning.
- [ ] L02 — Later, design a real inbox adapter, sender authentication, thread
  matching, access configuration, and outbound-message policy with separate tests.
  Real sending is outside the initial demo.

Next work: B13 and E02–E04, followed by the contact-only agent path A01–A05.
UI work can proceed against existing endpoints once U01 establishes its baseline.
