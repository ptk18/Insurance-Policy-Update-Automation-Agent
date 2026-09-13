# Demo recording script (V09)

The owner reported all three local Gemini/dashboard scenarios passing on 2026-09-13.
Case IDs, timings, and videos have not been recorded yet; no hosted result is implied.

Record the dashboard with synthetic data only. Keep AI Studio, `.env`, terminals
containing credentials, browser cookies, and developer request headers out of frame.
Record the configured model name separately; the dashboard only shows whether the agent
loop is configured. A fake browser-test video must not be presented as a Gemini run.

## Clip 1 — Valid request and human approval

1. Fresh workspace, Alex Morgan, DEMO-1001.
2. Paste: “Please update the email address for policy DEMO-1001 to
   sam.updated@example.com.”
3. Process; show extracted proposal and its Activity tool outcomes.
4. Show that no update is applied before approval.
5. Approve the exact version, then apply. Show completed values, confirmation draft,
   update audit, and persistence after refresh.

## Clip 2 — Missing evidence and same-case continuation

1. Fresh workspace, Alex Morgan, DEMO-1001. Request mailing address “42 Orchard Lane,
   Demo City, 10001” without attaching evidence.
2. Show the pause, missing-evidence finding, unsent follow-up, and unavailable approval.
3. Add information to the same case with `proof-matching.pdf` and a short reply.
4. Show new proposal version, Page 2 evidence, and cleared findings. Resume if offered.
5. Approve/apply; show completed outcome and the original pause in history.

## Clip 3 — Conflicting evidence and correction

1. Fresh workspace; submit the same address request with the conflicting PDF from Sample
   library. Show that the evidence conflict blocks approval.
2. Add a reply with the matching PDF to the same case. Show the new proposal, corrected
   evidence, and retained conflicting version in history.
3. Approve/apply; show saved result. If time allows, demonstrate execution replay
   returning the original receipt using the authenticated API, with credentials hidden.

For each clip record: date, commit, actual model, input/sample, expected/observed
status, proposal version, and elapsed time measured from submission to review. Record
quota errors and retries rather than excluding them silently. If waiting is shortened in
editing, label the cut; do not present edited runtime as latency. Report “3 synthetic
scenarios, manually tested” until a separately measured sample exists. No accuracy,
savings, insurer integration, or production-readiness claim.

Videos and hosted acceptance remain pending. Add their filenames/links and actual
measurement records to `process.md` after they exist.
