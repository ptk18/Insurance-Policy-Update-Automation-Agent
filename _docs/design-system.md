# Design baseline and change record

Last inspected: 2026-09-12. Read before changing the UI. Scope comes from
[plan.md](plan.md); delivery tasks live in [process.md](process.md).

## Current baseline: Minimal review workspace (D003)

The Next.js/React dashboard is implemented in [frontend](../frontend/).
Open port **3000** for the product; port 8000 `/docs` is the API explorer.
The UI uses the existing backend and shows persisted synthetic case data.
It creates no example cases until the guest submits a request.

### Source of truth

- [globals.css](../frontend/app/globals.css): visual roles, layouts, and shared
  component states. Keep new visual rules here or extract a shared component;
  do not introduce a second theme or inline one-off colors.
- [types.ts](../frontend/lib/types.ts): shared status labels and API contracts.
- [primitives.tsx](../frontend/components/primitives.tsx): status badges, notices,
  native modal dialogs with focus restoration, and timestamp formatting.
- [forms.tsx](../frontend/components/forms.tsx): intake, contact fields, edits,
  rejection reasons, and evidence correction.
- [dashboard.tsx](../frontend/components/dashboard.tsx): queue, counts, review,
  request/evidence, and activity views.

### Visual decisions

- Palette: page `#f7f8f5`, white surfaces, ink `#243730`, secondary text `#66756e`,
  borders `#e2e7e1`, primary green `#24674f`, hover `#194f3c`, focus `#39715d`.
  Use the CSS semantic variables for success, information, warning, and error.
- Typography: local Arial/Helvetica throughout. Main heading 24–26 px, case and
  dialog headings 20–22 px, primary content 12–14 px. Use plain descriptive headings
  and readable values. No display serif, slogans, or remote font requests.
- Spacing: 4/8/12/16/20/24/32/40 px scale. Desktop canvas padding 24 px; mobile
  padding 16 px. Radius 6 px for controls, 10 px for panels, 12 px for dialogs.
- Layout: one compact top header with Policy desk, Sample library, and Help.
  No sidebar, summary cards, decorative welcome illustration, or slogan footer.
  The page has one New request action, search/status controls, and the queue beside
  the review panel within a 1248 px canvas. Below 760 px the queue stacks above
  detail. The mobile comparison groups each field with labeled value columns.
- Navigation: show useful destinations as text buttons on desktop and mobile;
  keep Review, Request & evidence, and Activity as the three detail tabs.
  Counts belong next to the list title, not in another row of dashboard cards.
- Icons: Lucide React only; 1.7 stroke width. Icons supplement text or have an
  accessible label. Do not introduce another icon family.
- Motion: short hover transitions and a spinner only for actual queued/running
  activity; reduced-motion preference disables animations and transitions.

### Implemented interaction rules

- Guest entry explains fictional data. Bearer credentials stay in an HttpOnly
  SameSite=Strict cookie; the UI never asks a guest to copy an API token.
- The request count and status filter derive from the authenticated workspace. Search matches
  policy number, case identifier, or broker. Poll every two seconds while visible;
  responses from earlier selections/actions are discarded.
- Intake accepts English request text, an explicit policy number when available,
  simulated broker context, optional structured contact changes, sample evidence,
  and a text PDF up to 5 MB. Sample forms populate from the API fixtures.
- A saved intake survives upload/queue failure; retrying the dialog continues that
  case instead of creating another. No image/OCR claim is made.
- Review exposes the original request/replies, evidence source and page, findings,
  exact before/after values, unsent drafts, and historical versions.
- Address evidence conflicts block the whole request. No partial approval or waiver.
  Contact-only changes do not require address evidence.
- Approve is explicitly bound to the displayed proposal version. Apply is a
  separate action: `/resume` for a configured agent, `/execute` otherwise.
  Approved never means applied. No automatic approval and no outbound email.
- Edits/replies create a fresh version and invalidate approval. Dialogs capture the
  opening version; polling cannot silently retarget the submission. On 409, retain
  form input, close/refresh/review before another action. On 401/403/404, clear
  unavailable detail, including any open review dialog.
- Corrected PDFs are bound through a same-case reply. Stored files and fixture
  documents download through authenticated routes; they are not public assets.
- Persisted failed jobs show the sanitized error, attempts, retryability, and a
  manual retry button. Queued/running jobs show no invented percentage.
- Native dialogs trap focus and restore it on close; Escape closes an idle dialog.
  Tabs support arrow/Home/End keys. Labels, focus rings, notices, and status words
  must remain present; color alone must never communicate a state.

### Shared status vocabulary

`received` → Received; `processing` → Processing;
`awaiting_information` → Needs information; `awaiting_approval` → Ready for review;
`approved` → Approved · update pending; `completed` → Completed;
`rejected` → Rejected; `blocked` → Access blocked.

Job status is separate: queued, running, waiting, completed, or failed. A failed
job must remain visible even if the case itself still says Received/Processing.
Historical proposal states are shown as historical, never as current approval.

## Screenshot baseline and verification

The [browser suite](../frontend/tests/dashboard.spec.ts) captures these synthetic
states with `CAPTURE_BASELINE=1 npm test` after a production build. Wide viewport
is **1440 × 1050**, narrow **390 × 844**; full-page images may be taller.

- [Guest entry](screenshots/welcome-wide.png), [empty workspace](screenshots/empty-wide.png).
- [Ready for review](screenshots/ready-wide.png), [mobile review](screenshots/ready-mobile.png).
- [Missing evidence](screenshots/missing-wide.png), [conflicting evidence](screenshots/conflicting-wide.png),
  [corrected PDF](screenshots/corrected-wide.png).
- [Approved/pending](screenshots/approved-wide.png), [completed](screenshots/completed-wide.png),
  [rejected](screenshots/rejected-wide.png), [blocked access](screenshots/blocked-wide.png).
- [Stale edit](screenshots/stale-version-wide.png), [failed processing](screenshots/failed-wide.png).

Checks cover the real local API with temporary SQLite data, rule-based processing,
PDF inspection, and a scripted extraction failure/retry. They do not call Gemini.
Keyboard tabs, dialog focus/escape, and horizontal overflow are checked in Chromium.
Desktop/mobile review and evidence screenshots were visually inspected. These are
reference images, not pixel-difference regression tests or an accessibility certification.

Remaining: live-agent browser verification, Safari/Firefox, screen-reader and
formal contrast audits, automated visual comparisons, slow-network/loading and
large-queue behavior, and deployment. Image inspection and case chat stay deferred.

## Drift prevention

Before changing a component, identify its states and inspect shared CSS and status
mapping. Reuse the existing pattern. Run the affected synthetic browser scenario,
check keyboard and narrow layouts, and compare screenshots. Update this record and
[testing-guidelines.md](testing-guidelines.md) with actual evidence and remaining gaps.
Do not change status/action wording separately in list and detail.

## Change history

### D001 — 2026-09-12 — Backend-only inventory

Documentation only. The repository had no product components, CSS, or screenshots.
It recorded plan-derived constraints and proposed status conventions. Verified by
source inspection; no browser checks. That absence-of-UI baseline is superseded by
D002; its authorization, approval, and draft constraints remain in force.

### D002 — 2026-09-12 — First implemented review dashboard

Implemented the Policy desk visual system and core request-to-review workflow above.
Added the current tokens, reusable forms/notices/dialogs, responsive queue/detail,
source downloads, manual approval/application, correction/retry, and audit history.
Browser checks exposed and fixed local origin validation and dialog focus restoration.
Verification and screenshots are listed above; wider accessibility and hosted-agent
validation remain open. Supersedes the visual absence recorded in D001.

Append future decisions with date/ID, affected component/states, previous/new behavior,
reason, shared-code references, screenshots/viewports, actual checks, and remaining work.


### D003 — 2026-09-12 — Simplify the review workspace

Implemented at the user's request for a simple, minimal, easy-to-navigate UI.
Removed the sidebar, four summary cards, decorative entry graphics, slogans, and
footer. Replaced them with a compact header, short onboarding/empty-state copy,
plain sans-serif headings, and direct access to the request queue. Sample library
and Help remain visible as text buttons at all screen sizes. Shared statuses,
version-bound actions, evidence handling, and the three review tabs are retained.

Source: dashboard.tsx and globals.css linked above. Removed obsolete decorative
CSS rules. Updated the existing empty-state test selector and regenerated the
reference screenshots for this baseline. Verification uses the existing nine
isolated Chromium scenarios, production build, and TypeScript checks. Supersedes
D002's layout/typography; its workflow and approval constraints remain in force.

Future UI work should preserve this minimal baseline: add controls only when they
help complete a request; avoid decorative panels, repeated counts, or promotional copy.
