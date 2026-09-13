# Insurance Policy Update Automation Agent

A synthetic-data demo of broker-request review and human-approved contact updates.
The agreed product scope lives in [_docs/plan.md](_docs/plan.md).
See the [delivery checklist](_docs/process.md),
[test coverage guide](_docs/testing-guidelines.md), and
[design baseline](_docs/design-system.md) before extending the project.

## Current implementation

The first backend slice is runnable: FastAPI, Pydantic, SQLAlchemy, isolated guest
workspaces, seeded health policies and broker assignments, structured case intake,
a separate processing step, PDF/image attachments with PDF inspection, hosted-model
extraction of free-text requests, evidence validation, clarification drafts,
replies, proposal edits, approval, rejection, simulated policy updates, and an
audit timeline.

Intake and processing are separate operations. `POST /cases` only stores the
request (`received`); `POST /cases/{id}/process` queues a durable job (answer
`202`, case still `received`, `job.status` `queued`) that a worker claims and runs
outside the request: authorization, validation, and proposal preparation happen
in the worker's own transactions, so a failed run leaves the stored intake ready
to run again. Poll `GET /cases/{id}` until `job.status` leaves `queued`/`running`.

When an intake carries no structured `changes`, processing sends the request text
to the configured hosted model (Gemini, text only) and asks for a fixed JSON shape:
policy number, the three permitted contact fields, unsupported requests, and
ambiguities. The backend then applies its own controls: a value that does not
appear verbatim in the request text is dropped and reported (`unverified_extraction`),
the policy number is only ever the one stated in the text — never inferred from a
name — and unsupported or ambiguous wording pauses the case with
`unsupported_request`/`ambiguous_request` findings and a clarification draft. The
model never selects tools, never sees reviewer credentials, and never approves. A
model failure returns 503 (retryable) or 502 and leaves the case `received`. The
`request_extracted` audit event records the grounded result and token usage.
Structured intake skips the model entirely; without a configured key, free-text
intake pauses with `missing_changes` until a reviewer edits the proposal.

Attachments (PDF, PNG, JPEG; type detected from the bytes, 5 MiB default limit via
`MAX_ATTACHMENT_BYTES`) are stored in the database, scoped to the guest workspace
and case, and served only through authenticated case endpoints. PDF text layers are
inspected deterministically for labeled `Account holder:` and `Service address:`
lines, recording the page they came from and the reasons a document is unreadable
or uncertain. Any other document text is ignored. Image documents are stored but
reported uncertain: there is no OCR, and image/model inspection is deferred. Seven
synthetic sample documents are downloadable from `GET /fixtures`.

The eight agent tools from the plan exist as typed, case-scoped functions
(`src/policy_update/tools.py`): each validates a strict input, runs the same service
code as the review API, returns a structured result or error the model can observe,
counts against a bounded call budget, and is audited as `tool_called`. Approval,
rejection, and proposal edits are reviewer-only API operations and are not tools;
nothing in the tool layer takes a bearer token.

When a model key is configured, `POST /cases/{id}/process` runs the bounded
LangGraph loop (`src/policy_update/agent.py`) instead of the rule-based stand-in:
the model receives the goal, the eight tool declarations, and a case snapshot in
which the request text is marked as data, then chooses one tool per turn and reads
its result. Each tool call commits in its own transaction; the loop's own state is
checkpointed in the same database. A call that leaves the case awaiting
information or approval interrupts the loop; a reviewer reply or approval followed
by `POST /cases/{id}/resume` continues it (after approval the agent applies the
exact approved version; `/execute` remains available as the manual path). The loop
stops for human review with an `agent_stopped` finding when the model finishes
without a proposal or reaches the tool-call budget (`AGENT_TOOL_BUDGET`, default
12). Every attempt is recorded on a durable job (`job` in the case view:
action, `queued|running|waiting|completed|failed`, attempts, `retryable`,
sanitized `last_error`, `worker_id`, `lease_expires_at`) with
`processing_queued`/`processing_failed`/`processing_finished` timeline events. A
model failure mid-loop fails the job (retryable for an outage) and leaves the case
`processing` with its checkpoint; `POST /cases/{id}/process` or `/retry` continues
from the last completed step. The timeline shows `agent_decision` (tool plus the
model's one-sentence stated intent), `tool_called`, and `agent_finished` events —
never hidden reasoning. Set `AGENT_LOOP=off` to keep rule-based processing with
extraction only.

The worker (`src/policy_update/worker.py`) owns every run, rule-based or agent.
The queue is the `processing_jobs` table: a claim is a compare-and-set update that
turns a `queued` job into `running` under this worker's ID and a lease
(`JOB_LEASE_SECONDS`, default 90) that a heartbeat renews while the run is alive,
and every processing step re-checks ownership inside its own transaction, so a
worker that paused past its lease stops rather than acting on a case another
worker has taken over. Any worker's poll sweeps lapsed leases back into the queue
(`processing_stalled`) until `MAX_JOB_ATTEMPTS` (default 5), after which the job
fails visibly for a manual `POST /cases/{id}/retry`. `WORKER_MODE=embedded` (the
default) runs one worker thread inside the API process so a single `uvicorn` is a
complete demo; `WORKER_MODE=external` makes the API queue only, with one or more
`uv run python -m policy_update.worker` processes over the same database doing
the work. `GET /health` reports the mode.

The Next.js review dashboard in `frontend/` provides guest entry, sample intake,
PDF uploads, a searchable case queue, before/after comparison, version-bound edits
and approvals, rejection reasons, corrected evidence, processing/retry feedback,
unsent drafts, and persisted activity. The browser polls the existing API; it does
not run the agent itself. **Image inspection and deployment are still pending.**
Request text is untrusted input: the model
only extracts from it, and every extracted value is checked against the text.
Callers may supply the policy number and structured changes explicitly; the
extraction path fills them from the text when they are omitted. Address evidence
is either a named server-owned fixture or an uploaded document. Drafts use
templates.

## Run locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node.js 22+ with npm
for the dashboard (Next.js requires at least Node.js 20.9).

```sh
uv sync --locked
cp .env.example .env   # add GEMINI_API_KEY to enable free-text extraction
uv run uvicorn policy_update.api:create_app --factory --reload
```

That single process also runs the job worker (`WORKER_MODE=embedded`). To run the
worker separately — the deployment shape — start the API with
`WORKER_MODE=external` and, in another terminal over the same `DATABASE_URL`:

```sh
uv run python -m policy_update.worker
```

### Open the dashboard

Keep the API and any external worker running. In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:3000> and choose **Open demo workspace**, then **New request**.
If port 3000 is occupied, use `npm run dev -- --port 3002` and open
<http://127.0.0.1:3002> instead.
Use a sample or paste a request, review the proposed changes, choose **Approve v…**,
then **Apply approved update**. With the agent enabled, applying queues `/resume`;
without it, the dashboard calls the version-bound `/execute` endpoint. A reply
revalidates evidence immediately; **Resume processing** is available when the
configured agent still needs to continue an information request.

The frontend connects to `http://127.0.0.1:8000` by default. For a different API,
start it with `env POLICY_API_URL=http://127.0.0.1:8001 npm run dev`. This variable is
server-only. Do not put the Gemini key in the frontend or a `NEXT_PUBLIC_*` variable.
Guest bearer tokens stay in an HttpOnly, SameSite=Strict cookie; same-origin Next.js
routes forward authenticated calls and downloads. A browser workspace is separate
from workspaces created by the CLI demo or Swagger. Existing cases in those other
workspaces do not automatically appear here. The cookie lasts seven days; backend
guest cleanup/expiry is still pending.

For a production build, run `npm run build` followed by `npm start`. Browser tests
and screenshot regeneration are documented in the [testing guide](_docs/testing-guidelines.md).

### Backend configuration

The API owns schema bootstrap; a worker started first waits until the tables
exist. Keep `JOB_LEASE_SECONDS` (default 90) at least twice the longest single
step — a hosted-model call is bounded at about 70 s including its retry — because
the heartbeat renews the lease at a third of its length and waits for the step's
row lock on PostgreSQL.

The app factory loads `.env` from the working directory (or the file named by
`POLICY_UPDATE_ENV_FILE`) without overriding variables already set in the shell.
`.env` is gitignored; keep keys out of commits, logs, and issue reports. The key is
sent only in the `x-goog-api-key` header. Without `GEMINI_API_KEY`, `GET /health`
reports `"extraction": "unconfigured"` and free-text intake pauses for a reviewer.
`GEMINI_MODEL` overrides the default `gemini-3.8-flash`. Free-tier requests are
rate limited and may answer 429/503; the adapter retries once, then the job fails
as retryable so `POST /cases/{id}/retry` can continue it later. An agent run makes roughly five
to seven model calls per case, so a full demo can exhaust the free per-minute quota
of the larger Flash models; `GEMINI_MODEL=gemini-3.5-flash-lite` has more headroom
and completed the demo scenarios.

Open <http://127.0.0.1:8000/docs> for the interactive review API. SQLite persists to
`policy_demo.db` by default. Startup creates missing tables and adds missing
*nullable* columns (such as the job lease columns) to existing ones; it never
resets data. A `policy_demo.db` created before the non-nullable
`cases.requested_changes` column existed must still be deleted or replaced with a
fresh `DATABASE_URL`; versioned migrations are still pending.

### Troubleshooting processing and retries

`GET /` and `/favicon.ico` on **port 8000** return 404 because this port serves the
API. The dashboard runs on **port 3000**; `/docs` on port 8000 is the API explorer.
`POST /cases/{id}/process` returning 202 means the job was queued, not
that model processing succeeded. Repeated 200 responses from `GET /cases/{id}`
are normal polling; inspect the response's `job.status` and `job.last_error`.

Model failures now retain an allowlisted diagnostic such as `HTTP 429
RESOURCE_EXHAUSTED`, `HTTP 503 UNAVAILABLE`, `HTTP 401 UNAUTHENTICATED`, or
`ReadTimeout`. For quota errors, check the project's model limits in AI Studio
and retry after quota is available; for authentication/configuration errors, fix
the configuration first. Do not assume every retryable error is a quota problem.
An older saved generic error cannot be diagnosed retroactively.

Restart both the API and separate worker after code or model-configuration changes.
To use the separate-worker setup explicitly, run these in different terminals
from the same project directory:

```sh
env WORKER_MODE=external uv run uvicorn policy_update.api:create_app --factory
uv run python -m policy_update.worker
```

`/health` reports the API's worker mode. Without `external`, the API also runs an
embedded worker that may claim the job before the separate worker. After correcting
the cause, retry the existing case through `/cases/{id}/retry` using its guest
session; the worker continues its saved checkpoint.

### Run the smoke scenarios

In another terminal, run the scenarios (contact-only, missing evidence with a
reply, conflicting evidence with a corrected reply, a conflicting uploaded PDF
corrected by a second upload, and — when the server has a model key — a free-text
request extracted by Gemini plus one with an unsupported change that pauses):

```sh
uv run python scripts/demo.py
```

The script creates a new isolated guest, submits and processes each intake,
performs simulated reviewer approvals, executes each update, and checks duplicate
execution. It keeps the guest token in memory and never prints it. This is an API
smoke demo; it polls each queued job until the worker finishes it, retries a
retryable job failure through `/retry`, and — with a configured key, when every
`/process` is a live agent run — prints the tool sequence the model chose and
resumes the loop after each approval.

For manual review through `/docs`:

1. Call `POST /workspaces`, then enter its returned token in **Authorize**. Keep
   this token to return to the same workspace after a restart.
2. Call `GET /fixtures` and copy a sample's `intake` object into `POST /cases`.
   The response is the stored `received` case with no proposal yet. Samples
   without `changes` exercise model extraction when a key is configured.
3. Optionally download a sample document from `GET /fixtures/documents/{id}` and
   upload it with `POST /cases/{id}/attachments`. An upload to a `received` case
   becomes its evidence; the response shows the inspection result and page.
4. Call `POST /cases/{id}/process` (answer `202`: the job is queued), then
   `GET /cases/{id}` once `job.status` is no longer `queued`/`running` and inspect
   the before/after values, findings, evidence source, and (in agent mode) the
   `agent_decision` and `tool_called` timeline entries. Processing a completed case
   returns 409; a case left `processing` by a model failure continues where it
   stopped through `/process` or `/retry`.
5. For missing/conflicting evidence, call `POST /cases/{id}/replies` with
   `{"expected_version": 1, "text": "Corrected evidence", "evidence_id": ...}` where
   `evidence_id` is a fixture name such as `matching-address` or the ID of an
   attachment uploaded to this case.
6. Approve the case's `current_version` with `POST /cases/{id}/approve`, then either
   call `POST /cases/{id}/resume` (agent mode: the agent applies the approved
   version) or `POST /cases/{id}/execute` with the same `{"version": ...}` body.
7. Inspect `GET /cases/{id}` for the confirmation draft and timeline. Execute the
   same version again to retrieve the original receipt.

The reviewer token identifies the guest workspace. Broker selection represents
a **simulated** identity from the sandbox's two seeded brokers; it does not verify
an email sender or establish real broker authentication.

## Database and checks

Set `DATABASE_URL` in your shell to use PostgreSQL with the SQLAlchemy psycopg
driver (`postgresql+psycopg://...`), or put it in `.env`. Use a fresh demo
database: schema migrations and deployment configuration are pending.

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

`scripts/evaluate_model.py` runs seven synthetic and adversarial request texts
through a running server with a configured key and checks backend invariants
(no inferred policy number, unsupported changes pause, injected text cannot skip
evidence or approval). It is a labeled synthetic measurement on a few examples,
not an accuracy or security claim; its last run matched 7/7 on
`gemini-3.5-flash-lite`.

The test suite never loads `.env` or calls a hosted model: `conftest.py` builds
the app with `model=None`, and extraction tests use a scripted `FakeModel` or an
`httpx.MockTransport` for the Gemini client.

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
  not log request bodies, bearer tokens, model keys, or document contents. Model
  error responses carry the HTTP status only. No email is sent.
- The model receives the request text as data. Extracted values must appear
  verbatim in the text; a stated policy number still passes the broker assignment
  check, so text cannot escalate access. In the loop the model can only call the
  eight typed tools, one per turn, within a budget; every call is validated,
  authorized, and audited by the backend, and approval is not a tool.

The future agent's allowlist must expose only the permitted processing tools from
the plan. It must not expose reviewer approval operations or receive a guest's
reviewer bearer token. Grounding and the tool contracts limit what an injected
instruction can change to values already present in the text and to actions the
backend validates anyway; no adversarial evaluation of the hosted model has been
run yet, so no broader prompt-injection resistance claim is made.

## Next implementation steps

1. Add image document inspection through the model adapter.
2. Verify the dashboard against the live agent and expand cross-browser and
   accessibility checks; the local core flows are covered with synthetic data.
3. Add database migrations, guest lifecycle limits, containers, and deployment;
   run the complete acceptance scenarios in the hosted environment.

Case chat and real inbox integration remain later phases.
