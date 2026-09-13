# Project instructions

## Read first

- Read [`_docs/plan.md`](_docs/plan.md) for agreed scope and acceptance criteria.
  It describes intended functionality, not completed implementation.
- Read [`README.md`](README.md) for setup and current implementation status.
- Read [`_docs/process.md`](_docs/process.md) for how work is organized, completed
  tasks, and the remaining delivery checklist.
- Before writing tests, read
  [`_docs/testing-guidelines.md`](_docs/testing-guidelines.md) for existing coverage
  and gaps. Update its inventory when coverage changes.
- For anything touching the UI, read
  [`_docs/design-system.md`](_docs/design-system.md). Record visual and interaction
  decisions there as they are implemented to prevent design drift.
- Inspect the working tree before editing. Preserve existing user changes,
  including documentation moves and uncommitted work.
- These instructions supplement the machine-wide agent safety policy; they do
  not remove its permissions or secret-handling requirements.

## Scope and delivery

Build a synthetic-data health insurance policy update demo. Only policyholder
mailing address, email, and phone updates are permitted. Prioritize one working
core workflow before case chat or real inbox integration.

The current implementation supports structured or free-text review inputs, server-owned
evidence fixtures, PDF/image attachments with deterministic PDF text-layer inspection,
and a text-only Gemini adapter (`GEMINI_API_KEY` loaded from `.env`) that extracts
requested changes and pauses unsupported or ambiguous requests, typed case-scoped tools,
and a bounded LangGraph loop in which the model selects tools, pauses on interrupts for
replies and human approval, and resumes from persisted checkpoints. Processing routes
only queue a durable job (`202`); a worker (embedded thread by default, or a separate
`python -m policy_update.worker` process) claims it under a renewed lease, runs it
outside any request, and sweeps stalled jobs back into the queue. Image/OCR inspection
and deployment remain pending. The Next.js dashboard in `frontend/` connects through
same-origin route handlers and an HttpOnly guest cookie. Check the code before
describing a planned feature as implemented, and update the README when that status
changes. Tests must pass `model=None`/`agent_model=None` or scripted fakes (`FakeModel`,
`FakeChat`) to `create_app`; never call the hosted model from the suite. Tests run with
`WORKER_MODE=external` and drive the worker themselves (`helpers.run`/`drain`); do not
rely on a background thread for determinism.

Do not introduce real insurance records, outbound email, a vector database, model
training, multi-agent architecture, or a separate planning service for this scope.
Keep illustrative business rules and synthetic measurements labeled as such.

## Repository map

- `frontend/app/`: Next.js dashboard entry, shared CSS tokens, guest session routes,
  and an allowlisted API proxy. `POLICY_API_URL` is server-only; never expose
  bearer tokens or provider keys to the client.
- `frontend/components/`: queue/review UI, intake and version-bound action forms,
  dialogs, notices, and shared status badges; `frontend/lib/types.ts` holds API
  contracts and the shared case-status vocabulary.
- `frontend/tests/`: Playwright checks against a temporary SQLite API with a
  scripted extraction fake and no agent model. Never point browser tests at the
  user's live model-enabled API. Build first; run with `cd frontend && npm test`.
- `src/policy_update/api.py`: FastAPI routes, guest authentication, request
  transactions, and error responses.
- `src/policy_update/service.py`: case lifecycle, authorization, proposal
  versioning, reviewer actions, execution, and audit operations.
- `src/policy_update/models.py`: SQLAlchemy persistence models.
- `src/policy_update/database.py`: database sessions and revision checks; `migrations/`
  contains packaged Alembic revisions, `migrate.py` is the explicit upgrade command.
- `src/policy_update/limits.py`: persistent budgets and guest expiry. `cleanup.py`
  previews/deletes expired guests offline, including checkpoint threads.
- `_docs/deployment.md`: Docker/Render setup, migration/cleanup, and hosted checks.
- `src/policy_update/schemas.py`: strict Pydantic request contracts.
- `src/policy_update/validation.py`: permitted fields and evidence/contact checks.
- `src/policy_update/documents.py`: attachment type sniffing and labeled-field PDF
  inspection; image inspection is deferred (no OCR).
- `src/policy_update/extraction.py`: hosted-model adapter (Gemini `generateContent`
  over REST with a JSON schema), verbatim grounding of extracted values, and
  retryable/non-retryable model errors. `settings.py` loads `.env` explicitly.
- `src/policy_update/tools.py`: the eight typed, case-scoped agent tools, their JSON
  schemas, the call budget, and `tool_called` auditing. Never add approve/reject/edit
  or anything that takes a bearer token here.
- `src/policy_update/agent.py`: the LangGraph loop (`decide → act → wait | finish`),
  interrupts, per-step transactions, checkpointer construction, the in-process
  per-case run lock, and the per-run job-ownership guard. Mandatory controls belong
  in tools/service, not here.
- `src/policy_update/worker.py`: the job worker — queue polling, compare-and-set
  claims, lease heartbeat, stalled-job sweep, one attempt per claimed job, and the
  `python -m policy_update.worker` entry point. `runtime.py` builds the shared
  stack (database, models, agent runner, worker) for the API and the worker.
- `src/policy_update/fixtures.py`: fictional brokers, evidence, sample requests, and
  sample document metadata; `assets/` holds the generated synthetic PDFs/PNG
  (regenerate with `scripts/make_evidence_assets.py`).
- `tests/`: workflow, isolation, approval, concurrency, recovery, attachment,
  extraction, tool, agent-loop, worker, and adversarial tests; `tests/helpers.py`
  holds shared API helpers (`run`/`drain` queue a route and run the worker inline),
  `FakeModel`, `FakeChat`, and `upload_doc`.
- `scripts/evaluate_model.py`: labeled synthetic live evaluation of the configured
  model against backend invariants; never run it from tests.
- `scripts/demo.py`: local API scenarios with simulated reviewer approvals; in
  agent mode it prints model-chosen tool sequences and resumes after approval, and
  the free-text scenarios run only when the server reports a configured model.
- `.github/workflows/ci.yml`: SQLite and PostgreSQL checks.

## Invariants to preserve

- Scope every case, policy, and future attachment operation to the authenticated
  workspace. Check broker assignment before revealing policy values or changing
  them, including historical proposal views after access is revoked.
- Require an explicit policy number. Never infer a policy from a name or email,
  and never treat an email's claimed sender as an authenticated broker.
- Enforce permitted fields and validation in backend code. Email text and document
  contents are untrusted evidence, never instructions granting permissions.
- Treat all changes in a request as one unit. Missing, uncertain, unreadable, or
  conflicting required evidence blocks the entire proposal. Reviewers cannot
  waive evidence conflicts. Contact-only changes need no address evidence.
- Bind human approval to the exact proposal version. Edits and replies rerun
  validation and invalidate prior approval; stale browser actions must fail.
- Recheck authorization, evidence, and policy revision at approval and execution.
  Changed policy state requires a new proposal and fresh approval.
- Commit policy changes, the execution receipt, case completion, and the audit
  outcome together. Keep the proposal ID as the stable idempotency key; repeated
  successful execution returns the saved outcome without another update.
- Keep drafts unsent. Show tool outcomes and concise decision summaries in the
  timeline, never hidden model reasoning.

## Implementation conventions

Use Python 3.12+, FastAPI, Pydantic, and SQLAlchemy. Use `uv` for dependencies and
keep `uv.lock` synchronized with `pyproject.toml`. Follow Ruff's configured style.

Keep routes thin and business controls in reusable domain operations. Future
agent tools must reuse those controls rather than provide alternate write paths.
Keep intake separate from processing as the agent integration is introduced.

The LangGraph integration must let the LLM select from typed, bounded tools, with
durable checkpoints, human approval interruption, and a tool-call budget. Never expose
approval operations or reviewer credentials to the model. Do not present a fixed
sequence of prompts or the current fixture workflow as a completed agent. Processing
jobs must survive browser requests and support retry.

Support SQLite for local development and PostgreSQL for the deployed direction. Do not
replace transactional or concurrency guarantees with process-local locks. Schema changes
require a new packaged Alembic revision. Existing databases upgrade through the explicit
migration command; deployed API/workers use SCHEMA_MODE=verify. Never migrate the user’s
running database without an approved maintenance step.

## Commands and verification

```sh
uv sync --locked
uv run uvicorn policy_update.api:create_app --factory --reload
uv run python scripts/demo.py
uv run ruff check .
uv run ruff format --check .
uv run pytest -q --tb=short
```

Run the demo script only against the intended local synthetic-data API. It creates
records, simulates reviewer approvals, and executes updates.

For backend behavior changes, run relevant tests and lint/format checks. Add
meaningful regression tests for authorization, approval, validation, or recovery
changes. Run the suite against a dedicated PostgreSQL test database through
`TEST_DATABASE_URL` when changing persistence or concurrency behavior; tests leave
synthetic records there. Do not use a production or shared business database.
Documentation-only edits need reference checks, not the full test suite.

Report what changed, what was actually verified, and what remains unfinished.
Distinguish fixture-based checks from real document extraction or LLM evaluation.

## Access and secrets

Follow the user's machine-wide permission rules: local writes require explicit
authorization, and third-party connectors are read-only. Do not push, publish,
deploy, send messages, or mutate external service state through a connector.

Do not read `.env`, key files, credential JSON, or shell history unless explicitly
requested or essential to the authorized task. Never print, copy, or commit
secrets. Avoid logging request bodies, tokens, document contents, or database
credentials. Do not dump environments or sensitive process arguments.

Do not run destructive commands, migrations, deployments, or paid model calls
without explicit approval. Preserve existing work and keep changes within the
authorized task.
