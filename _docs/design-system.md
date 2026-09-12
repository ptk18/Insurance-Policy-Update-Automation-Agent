# Design baseline and change record

Last inspected: 2026-09-12. Read this file before work that touches the UI.
Scope comes from [plan.md](plan.md); delivery tasks live in
[process.md](process.md), especially U01–U07.

## Current baseline: no product UI implemented

The repository contains a FastAPI backend, generated API documentation, and a CLI
smoke demo. There is no Next.js/React app, CSS, component library, design-token
file, frontend test setup, or product screenshot baseline in the current tree.

[workflow.png](workflow.png) illustrates the business process. It is not a visual
specification for the dashboard. Swagger `/docs` is an API development interface;
its styling and manual token entry are not the intended guest onboarding design.

**No product visual changes have been implemented yet.** Do not treat colors,
fonts, component styles, breakpoints, or layout choices as established decisions.
The sections below separate existing behavior from proposed UI guidance and the
decisions that must be recorded when the first interface is built.

## Existing behavior the UI must preserve

These are product/backend constraints, not evidence of finished screens. Sources:
[API](../src/policy_update/api.py), [service](../src/policy_update/service.py), and
[schemas](../src/policy_update/schemas.py).

- The workspace and selected broker are simulated. Explain the synthetic demo
  context without exposing bearer tokens or backend internals in the product flow.
- The only editable policy fields are mailing address, email, and phone. Read-only
  identity context must not appear editable.
- Display original request/replies, supporting evidence, validation findings,
  and the exact current-versus-proposed values before approval.
- A request is one unit. Missing or conflicting required evidence prevents approval
  of all its changes; do not offer a waiver or a partial-apply shortcut.
- Editing or adding a reply creates a new proposal version and invalidates prior
  approval. Show that review is needed again without implying the old approval applies.
- Approval is an explicit reviewer action tied to the version on screen. It is
  separate from successful execution. Never show completion on approval alone.
- Follow-ups and confirmations are drafts. Do not present a Send action or imply
  that an email was delivered in the initial release.
- The timeline presents actor, time, action, version, and outcome. Model tool
  summaries, when added, must not expose hidden reasoning.
- Denied access must not reveal historical policy values. Hiding a button does
  not replace backend authorization.

## Status vocabulary and intended presentation

The API values below exist now. The human-readable labels and action presentation
are **proposed conventions for the first UI**, not shipped components. Record any
changes when implementing them. Share one status mapping across list and detail;
do not invent synonymous labels independently on each screen.

- `processing` → **Processing**. The backend currently uses this as an initial
  transient value; a durable worker/progress experience is pending. Do not fabricate
  percentages, tool activity, or an active job when none exists.
- `awaiting_information` → **Needs information**. Explain the blocking findings,
  show the clarification draft, and provide the same-case reply/evidence path.
  Approval is unavailable while findings remain unresolved.
- `awaiting_approval` → **Ready for review**. Show the latest version and evidence
  before offering Edit, Approve, and Reject.
- `approved` → **Approved — update pending**. Keep this distinct from Completed.
  Current execution requires a separate API call; future agent integration must
  define how execution starts and how its progress is reflected.
- `completed` → **Completed**. Show the persisted outcome and confirmation draft.
  Keep history readable; do not offer proposal edits or another approval.
- `rejected` → **Rejected**. Show the review decision/reason. The case is terminal;
  no reopen path is implemented.
- `blocked` → **Access blocked**. Explain denied broker access without exposing
  policy values. Do not suggest that a new evidence upload can bypass access checks.

Proposal statuses are a separate concept: `invalid`, `pending`, `approved`,
`superseded`, `rejected`, and `applied`. Show old versions as historical; a past
approval on a superseded version must never look actionable.

There is no persisted failed/retryable job status yet. Until A06 is implemented,
display actual API errors without claiming that a background retry is scheduled.
For 409 responses, preserve unsaved input where possible and require a reload/
comparison of the latest state before resubmitting an approval. For 401/403/404,
show an appropriate unavailable/session state without leaking another guest's data.

## Planned screen and component inventory

All items below are unimplemented. The first UI should cover the core flow before
adding chat or inbox features.

- [ ] Guest entry and sample selection: explain fictional data and open an isolated
  workspace without making the user manage technical credentials.
- [ ] Request intake: pasted English email, simulated broker context, explicit
  policy number where needed, attachment selection, and useful validation feedback.
- [ ] Case list: consistent status labels, policy/request context, and a clear way
  to open the next case requiring attention. Filtering details remain undecided.
- [ ] Case detail: a readable hierarchy for request/replies, evidence/source viewer,
  validation findings, and current/proposed contact values.
- [ ] Review controls: editable proposal, version context, explicit approval,
  rejection reason, and feedback when an edit or stale policy requires fresh review.
- [ ] Information request and correction: clearly labeled draft, missing/conflicting
  evidence explanation, same-case reply/upload, and resume feedback.
- [ ] Execution outcome: pending/applied/failure presentation, backend-supported
  retry, saved changes, and unsent confirmation draft.
- [ ] Audit timeline: readable timestamps, actors/actions/outcomes, version history,
  and supporting references with progressive detail where useful.
- [ ] Shared primitives: buttons, fields, status badges, notices, loading/empty
  states, and any dialogs introduced by the implemented flows.

Reuse one implementation of each shared pattern. Decide the case layout and
navigation before duplicating structure across routes. This document does not
prescribe a sidebar, modal, grid width, or other layout that has not been designed.

## Visual foundations to establish in U01

**All values remain undecided.** When implementing the first screen, record the
chosen values and link the actual token/component files here. Those shared code
definitions should become the source of truth for visual values.

- [ ] Color roles: page/surface backgrounds, text/muted text, border, primary action,
  focus, and semantic information/warning/error/success states, including variants.
- [ ] Typography: font family/fallbacks, body/label/heading sizes, line heights, and
  weights; readable presentation for long policy values and document text.
- [ ] Layout: spacing scale, content width, responsive breakpoints, list/detail
  behavior on narrow screens, and placement of the review controls.
- [ ] Shape and depth: field/button sizing, border widths, radii, shadows, and
  overlay layers if needed.
- [ ] Icons and motion: one icon source, consistent sizes, meaningful text labels,
  restrained transitions, and reduced-motion behavior.
- [ ] Shared component states: default, hover, focus, disabled, busy, error, and
  success where meaningful. Do not encode status with color alone.

Avoid per-screen colors, spacing, or type sizes that duplicate shared roles.
When a real exception is needed, name its purpose in the change record and decide
whether it should become a shared variant. A new library or visual theme is a
deliberate design decision, not an incidental dependency choice.

## UI verification and drift prevention

For each UI change:

1. Identify the affected screen, component, and state above. Inspect existing
   components/tokens before adding a new pattern.
2. Check the same status/action wording in the case list, detail, and notices.
   Preserve the difference between validated, approved, and applied.
3. Verify the affected flow with synthetic data and real backend outcomes. Inspect
   loading, empty, failure, disabled, long-content, and stale-version states when
   applicable; do not rely only on a successful fixture screenshot.
4. Check keyboard navigation, visible focus, labels/error association, readable
   contrast, status announcement, and focus handling for any dialog. Verify narrow
   and wide layouts with long addresses and evidence references.
5. Save representative screenshots with the viewport, route, and case state, and
   compare them to the current baseline. Store/link them in the change record when
   the first UI exists; no screenshot directory or browser test suite exists yet.
6. Update this file in the same change: implemented decisions, component/token
   references, verification evidence, and remaining gaps. Update the test inventory
   when adding browser/component/visual checks.

For the first baseline, capture ready-for-review, missing evidence, conflicting
evidence, corrected evidence, approved/pending execution, completed, rejected,
access blocked, and stale-proposal/error states. Capture transient worker/retry
states once their backend behavior exists. Reuse these scenarios for future
comparisons so a style change does not silently remove a workflow state.

## Design change record

### 2026-09-12 — D001: document the pre-UI baseline

- **Status:** documentation only; no visual implementation.
- **Observed:** backend data supports proposals, findings, history, and draft
  messages. No frontend components, tokens, or product screenshots exist.
- **Recorded:** plan-derived interaction constraints, proposed status labels,
  an unimplemented component inventory, and the visual decisions still needed.
- **Evidence:** current source tree, API/service/schemas linked above, and plan.
- **Verification:** source inspection and documentation reference checks; no
  browser, accessibility, or visual testing performed.
- **Remaining:** U01–U07 and all unchecked design items in this file.

Append an entry for each meaningful visual or interaction change. Use this form
and distinguish proposed from implemented decisions:

```text
Date / decision ID / title:
Status: proposed | implemented | superseded
Screen/component and states affected:
Previous behavior/appearance:
New behavior/appearance and reason:
Shared tokens/components changed (file references):
Screenshots and viewport/case state:
Checks actually performed:
Remaining work or intentional exceptions:
Supersedes decision ID (if applicable):
```

Keep history when a decision changes, and update the current baseline at the same
time. Do not leave an obsolete choice presented as current or mark a proposed
design as implemented without code and visual evidence.
