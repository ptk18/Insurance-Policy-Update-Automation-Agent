# Insurance Policy Update Automation Agent

A synthetic-data demo of broker-request review and human-approved contact updates.
The agreed product scope lives in [_docs/plan.md](_docs/plan.md).
See the [delivery checklist](_docs/process.md),
[test coverage guide](_docs/testing-guidelines.md), and
[design baseline](_docs/design-system.md) before extending the project.

## Current implementation

The first backend slice is runnable: FastAPI, Pydantic, SQLAlchemy, isolated guest
workspaces, seeded health policies and broker assignments, structured case intake,
a separate processing step, PDF/image attachments with PDF inspection, evidence
validation, clarification drafts, replies, proposal edits, approval, rejection,
simulated policy updates, and an audit timeline.

Intake and processing are separate operations. `POST /cases` only stores the
request (`received`); `POST /cases/{id}/process` runs authorization, validation,
and proposal preparation in its own transaction, so a failed processing request
leaves the stored intake ready to process again. Processing is currently a
synchronous rule-based stand-in for the planned worker, not an agent run.

Attachments (PDF, PNG, JPEG; type detected from the bytes, 5 MiB default limit via
`MAX_ATTACHMENT_BYTES`) are stored in the database, scoped to the guest workspace
and case, and served only through authenticated case endpoints. PDF text layers are
inspected deterministically for labeled `Account holder:` and `Service address:`
lines, recording the page they came from and the reasons a document is unreadable
or uncertain. Any other document text is ignored. Image documents are stored but
reported uncertain: there is no OCR, and image inspection waits for the model
adapter. Seven synthetic sample documents are downloadable from `GET /fixtures`.

**The LLM agent, LangGraph checkpoints/jobs, image inspection, Next.js dashboard,
and deployment are still pending.** Email text is stored as untrusted evidence; it
is not parsed yet. Callers supply the explicit policy number and, optionally,
structured proposed changes; without them processing pauses with a
`missing_changes` finding until a reviewer edits the proposal. Address evidence is
either a named server-owned fixture or an uploaded document. Drafts use templates.

## Run locally

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run uvicorn policy_update.api:create_app --factory --reload
```

Open <http://127.0.0.1:8000/docs> for the interactive review API. SQLite persists to
`policy_demo.db` by default. Startup creates missing tables (including the new
`attachments` table); it does not reset data and does not add columns to existing
tables. A `policy_demo.db` created before the `cases.requested_changes` column
existed must be deleted or replaced with a fresh `DATABASE_URL`; versioned
migrations are still pending.

In another terminal, run all four scenarios (contact-only, missing evidence with
a reply, conflicting evidence with a corrected reply, and a conflicting uploaded PDF
corrected by a second upload):

```sh
uv run python scripts/demo.py
```

The script creates a new isolated guest, submits and processes each intake,
performs simulated reviewer approvals, executes each update, and checks duplicate
execution. It keeps the guest token in memory and never prints it. This is an API
smoke demo, not an agent run.

For manual review through `/docs`:

1. Call `POST /workspaces`, then enter its returned token in **Authorize**. Keep
   this token to return to the same workspace after a restart.
2. Call `GET /fixtures` and copy a sample's `intake` object into `POST /cases`.
   The response is the stored `received` case with no proposal yet.
3. Optionally download a sample document from `GET /fixtures/documents/{id}` and
   upload it with `POST /cases/{id}/attachments`. An upload to a `received` case
   becomes its evidence; the response shows the inspection result and page.
4. Call `POST /cases/{id}/process`, then inspect the returned case's before/after
   values, findings, and evidence source. Processing a case twice returns 409.
5. For missing/conflicting evidence, call `POST /cases/{id}/replies` with
   `{"expected_version": 1, "text": "Corrected evidence", "evidence_id": ...}` where
   `evidence_id` is a fixture name such as `matching-address` or the ID of an
   attachment uploaded to this case.
6. Approve the case's `current_version` with `POST /cases/{id}/approve`, then call
   `POST /cases/{id}/execute` with that same `{"version": ...}` body.
7. Inspect `GET /cases/{id}` for the confirmation draft and timeline. Execute the
   same version again to retrieve the original receipt.

The reviewer token identifies the guest workspace. Broker selection represents
a **simulated** identity from the sandbox's two seeded brokers; it does not verify
an email sender or establish real broker authentication.

## Database and checks

Set `DATABASE_URL` in your shell to use PostgreSQL with the SQLAlchemy psycopg
driver (`postgresql+psycopg://...`). The app does not load `.env` files. Use a fresh
demo database: schema migrations and deployment configuration are pending.

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

To run the integration tests against a dedicated PostgreSQL test database, set
`TEST_DATABASE_URL` before running pytest. Tests create isolated guests and leave
their synthetic records in that database. The restart test always uses temporary
SQLite storage. CI runs the suite on SQLite and PostgreSQL 17.

## Enforced boundaries

- A workspace bearer token scopes every case operation and policy lookup. Only
  its hash is stored. Tokens do not yet expire; public deployment needs session
  expiry, resource limits, and guest cleanup.
- The backend checks the case's fixed broker assignment before returning policy
  values, preparing a proposal, approving it, or executing it. Request text cannot
  alter that identity. A stored but unprocessed case exposes only what the caller
  submitted, and no version-bound action can run on it until it is processed.
- Only mailing address, email, and phone changes are accepted. Any unresolved
  field or required evidence pauses the whole request. Evidence conflicts cannot
  be waived by the approval endpoint.
- Attachments belong to one case in one workspace; other workspaces receive 404.
  A reply can only bind evidence from the same case. Document text is evidence:
  inspection reads labeled fields only, so instructions inside a PDF change nothing.
- Every edit or reply creates a new proposal version. Older versions and their
  historical approvals remain visible but cannot execute. Stale browser actions
  are rejected using the expected version.
- Approval and execution recheck policy revision, evidence, and authorization.
  A policy change requires a new proposal and fresh approval.
- Policy writes, the unique proposal execution receipt, case completion, and the
  audit outcome commit in one transaction. PostgreSQL row locks and optimistic
  revisions protect concurrent operations. A repeated successful execution returns
  its saved result; a concurrent conflict can be retried manually.
- Audit records retain synthetic before/after values and attachment metadata
  (type, size, readability), not extracted document values. Application code does
  not log request bodies, bearer tokens, or document contents. No email is sent.

The future agent's allowlist must expose only the permitted processing tools from
the plan. It must not expose reviewer approval operations or receive a guest's
reviewer bearer token. No agent security or prompt-injection resistance claims are
made for the unfinished LLM integration.

## Next implementation steps

1. Add the actual LangGraph tool-selection loop, a hosted model adapter (including
   image document inspection), durable checkpoints, processing jobs, bounded tool
   calls, and manual retry handling.
2. Build the Next.js review dashboard around these endpoints.
3. Add database migrations, guest lifecycle limits, containers, and deployment;
   run the complete acceptance scenarios in the hosted environment.

Case chat and real inbox integration remain later phases.
