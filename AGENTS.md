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

The current implementation is a backend foundation with structured review inputs,
server-owned evidence fixtures, and PDF/image attachments with deterministic PDF
text-layer inspection. LLM processing (including image inspection), LangGraph
persistence/jobs, the Next.js dashboard, and deployment remain pending. Check the
code before describing a planned feature as implemented, and update the README when
that status changes.

Do not introduce real insurance records, outbound email, a vector database, model
training, multi-agent architecture, or a separate planning service for this scope.
Keep illustrative business rules and synthetic measurements labeled as such.

## Repository map

- `src/policy_update/api.py`: FastAPI routes, guest authentication, request
  transactions, and error responses.
- `src/policy_update/service.py`: case lifecycle, authorization, proposal
  versioning, reviewer actions, execution, and audit operations.
- `src/policy_update/models.py`: SQLAlchemy persistence models.
- `src/policy_update/database.py`: database setup and session factory.
- `src/policy_update/schemas.py`: strict Pydantic request contracts.
- `src/policy_update/validation.py`: permitted fields and evidence/contact checks.
- `src/policy_update/documents.py`: attachment type sniffing and labeled-field PDF
  inspection; image inspection waits for the model adapter.
- `src/policy_update/fixtures.py`: fictional brokers, evidence, sample requests, and
  sample document metadata; `assets/` holds the generated synthetic PDFs/PNG
  (regenerate with `scripts/make_evidence_assets.py`).
- `tests/`: workflow, isolation, approval, concurrency, recovery, and attachment
  tests; `tests/helpers.py` holds shared API helpers.
- `scripts/demo.py`: four local API scenarios with simulated reviewer approvals.
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

The planned LangGraph integration must let the LLM select from typed, bounded
tools, with durable checkpoints, human approval interruption, and a tool-call
budget. Never expose approval operations or reviewer credentials to the model.
Do not present a fixed sequence of prompts or the current fixture workflow as a
completed agent. Processing jobs must survive browser requests and support retry.

Support SQLite for local development and PostgreSQL for the deployed direction.
Do not replace transactional or concurrency guarantees with process-local locks.
Schema creation is currently bootstrap-only; add versioned migrations before
evolving a deployed database with existing data.

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
