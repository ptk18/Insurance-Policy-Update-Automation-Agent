# Design baseline and change record

Last inspected: 2026-09-13. Read before changing the UI. Scope comes from
[plan.md](plan.md); delivery tasks live in [process.md](process.md).

## Current baseline: Sunday orange review workspace (D008)

The Next.js/React dashboard is implemented in [frontend](../frontend/). The README
starts the product on port **3002** (Next.js defaults to 3000); port 8000 `/docs` is the
API explorer. The UI uses the existing backend and shows persisted synthetic case data.
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

- Palette: warm page `#faf9f7`, white surfaces, ink `#292522`, secondary text
  `#69615c`, and borders `#e8e3df`. Sunday orange `#FA4616` marks primary actions,
  selection, and the header accent. Orange buttons use a deeper action shade
  `#d9360b` with white text/icons and `#be2e08` hover. This retains readable
  contrast for compact 14px labels. The original `#FA4616` remains the brand accent. Small links and focus rings use darker orange `#b53210`,
  with `#fff0ea` selected surfaces. Semantic success/information/warning/error
  colors retain their separate meanings.
- Typography: local Arial/Helvetica throughout. Main heading 24–26 px, case and
  dialog headings 20–22 px, primary content 15–16 px, and supporting labels 14 px
  (compact header labels 12–13 px). Use plain descriptive headings and readable values. No display serif, slogans, or remote font requests.
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
  and a text PDF up to 5 MB. Labels say Paste email and Upload document. A shared,
  quiet notice in intake, correction, sample library, and Help explains English
  text/selectable-text PDF support and the lack of image/scanned-document support.
  Sample document options are collapsed until needed. Sample forms populate from
  the API fixtures.
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

## Browser states and verification

The [browser suite](../frontend/tests/dashboard.spec.ts) checks guest entry, empty
workspace, desktop/mobile review, missing/conflicting/corrected evidence,
approved/pending, completed, rejected, blocked access, stale edits, failed
processing, and slow submission. Wide viewport is **1440 × 1050**, narrow
**390 × 844**; full-page images may be taller.

Reference screenshots are saved in `screenshots/`:

- [Guest entry](screenshots/welcome-wide.png), [empty workspace](screenshots/empty-wide.png).
- [Ready for review](screenshots/ready-wide.png), [mobile review](screenshots/ready-mobile.png).
- [Missing evidence](screenshots/missing-wide.png), [conflicting evidence](screenshots/conflicting-wide.png),
  [corrected PDF](screenshots/corrected-wide.png).
- [Approved/pending](screenshots/approved-wide.png), [completed](screenshots/completed-wide.png),
  [rejected](screenshots/rejected-wide.png), [blocked access](screenshots/blocked-wide.png).
- [Stale edit](screenshots/stale-version-wide.png), [failed processing](screenshots/failed-wide.png),
  [saving request](screenshots/saving-request.png).

`CAPTURE_BASELINE=1 npm test -- --project=chromium` regenerates them for visual review.
The application and automated assertions do not depend on saved image files.

Checks cover the real local API with temporary SQLite data, rule-based processing, PDF
inspection, and a scripted extraction failure/retry. They do not call Gemini. Keyboard
tabs, dialog focus/escape, and horizontal overflow are checked in all three engines.
Desktop/mobile review and evidence screenshots were visually inspected. These are
reference images, not pixel-difference regression tests or an accessibility
certification.

Remaining: actual Safari/VoiceOver checks, broader loading/large-queue behavior, and
hosted verification. The three live Gemini browser scenarios were checked manually.
Chromium/Firefox/WebKit have workflow, axe contrast/accessibility, and delayed-intake
checks. Image inspection and case chat stay deferred.

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
Verification is described above; wider accessibility and hosted-agent
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


### D004 — 2026-09-13 — Contrast and cross-browser focus

Preserved D003's minimal layout. Changed `--muted` from `#66756e` to `#5d6c64` and
reused it for small evidence labels: axe measured insufficient contrast on the selected
queue background and the evidence-label surface. Modal opener buttons now explicitly
receive focus on activation, allowing WebKit to restore focus when Escape closes a
dialog. No extra navigation or decorative panels were added.

Verification: three browser engines, axe WCAG A/AA on the saved review states and
slow-intake modal, and desktop/390px review. Added the
saving-request reference state. Screenshots were
visually reviewed. Manual screen-reader checks and actual Safari remain open.

Guest-expiry behavior: an API 401 clears the guest cookie and selected case so “Open
demo workspace” can start a fresh session. This does not add a new screen.

### D005 — 2026-09-13 — Sunday orange and clearer dashboard copy

Refined the existing workspace at the user’s request for a minimal, comfortable UI.
Replaced the green brand palette with Sunday orange and warm neutral surfaces.
Dark text on the exact orange keeps primary actions readable; darker orange handles
small links and focus. Increased supporting text, comparison values, and main action
sizes. Mobile search and status filters use separate rows, and form fields use 16px
text on narrow screens. Retained the compact navigation and queue/review layout.

Revised entry, intake, help, document, progress, review, and completion copy. Paste
email describes the existing text input; Upload document describes the existing PDF
attachment control. There is no email-file import. A shared SupportNote explains
English and selectable-text PDF support without putting restrictions in field labels.
Sample document options use native disclosure. Technical evidence terms became
Sample document and Document text checked. Approval remains bound to the displayed
version, separate from applying the update; saved drafts remain visibly unsent.

Sources: globals.css, dashboard.tsx, forms.tsx, and primitives.tsx linked above.
Updated existing browser selectors to match visible labels; behavior coverage is
unchanged. Refreshed reference screenshots cover the same states and viewports.

Verification: frontend formatting, TypeScript, production build, and all 33 browser
checks passed across Chromium, Firefox, and WebKit, including axe WCAG A/AA checks,
keyboard/dialog behavior, approval/version safety, correction, and retry. All 14
reference screenshots regenerated; 1440px review, 390px review, and saving intake
were visually inspected. Tests use isolated synthetic data and scripted extraction;
no hosted model was called. Actual Safari/VoiceOver and hosted checks remain open.

### D006 — 2026-09-13 — Larger body text and white New request label

Increased body and comparison text to 16px, supporting copy to 14px, and most
controls to 15–16px. Body line-height is 1.65. New request uses white text and icon
on Sunday orange; its 19px bold label meets the large-text contrast threshold.
The hover uses a slightly darker orange. Compact header labels remain smaller to
keep navigation usable on mobile. Other primary buttons retain their existing text
color. Sources: globals.css and the dashboard New request button linked above.

The larger form exposed an existing keyboard-scroll problem while saving: every
control became unfocusable. The dialog close control now remains keyboard-focusable
and uses aria-disabled with an activation guard while busy. It cannot dismiss an
in-flight request, and the scrollable dialog remains accessible from the keyboard.

D006 verification: formatting, TypeScript, and production build passed. The full
browser run passed 30 checks and exposed the saving-dialog focus issue in all three
engines. After the fix, all six affected saving/keyboard/mobile checks passed across
Chromium, Firefox, and WebKit, including axe contrast and keyboard focus checks.
Refreshed reference images; desktop/mobile review and saving intake were visually
inspected. Synthetic data and scripted extraction only; no hosted model calls.

### D007 — 2026-09-13 — White labels on every orange button

Applied the user's white-text preference to the shared primary-button style, including
entry, intake, review, apply, and help actions. Icons inherit the same white color.
All orange buttons now share the existing New request 19px bold label and darker
orange hover to preserve large-text contrast on Sunday orange. Removed the per-button
exception. Secondary buttons and semantic status colors retain their existing roles.

D007 verification: formatting, TypeScript, production build, and all 11 Chromium
workflow checks passed, including axe contrast, keyboard/dialog behavior, and mobile
layout. Refreshed reference screenshots; desktop approved and mobile review states
were visually inspected. Synthetic data only; no hosted model calls. Firefox/WebKit
were not rerun for this shared color/style change.

### D008 — 2026-09-13 — Compact buttons and smaller labels

Reduced shared action buttons from the oversized 19px primary labels to 14px/600,
with 38px minimum height, 8px × 12px padding, and 16px icons. Small actions use 13px
labels and 32px height; icon controls use 36px squares. Text actions, tabs, and the
native file-picker button also use compact labels. Body and comparison text keep
the larger D006 reading sizes. Mobile actions retain their available full width.

White text remains on all orange actions. Buttons use a deeper brand-derived orange
`#d9360b` (4.68:1 with white) so compact labels remain readable; the header/selection
accent retains exact Sunday `#FA4616`. Hover is `#be2e08`. These shared rules in
globals.css supersede D007's 19px primary-button sizing.

D008 verification: formatting, TypeScript, production build, and all 11 Chromium
workflow checks passed, including axe contrast, keyboard/dialog behavior, and mobile
layout. Reference screenshots were refreshed; desktop and 390px mobile review states
were visually inspected. Existing coverage is unchanged. Synthetic data only; no
hosted model calls. Firefox/WebKit were not rerun for this CSS-only refinement.
