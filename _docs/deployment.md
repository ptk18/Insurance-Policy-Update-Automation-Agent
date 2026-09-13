# Deployment and maintenance runbook

Prepared 2026-09-13; not yet deployed to a host. Use synthetic records only.
[process.md](process.md) tracks actual verification.

## Prepared topology

`render.yaml` proposes a public Next.js dashboard, private FastAPI service, separate
worker, and managed PostgreSQL, all in Singapore. Both Python services use the same
Docker image and database. The frontend Docker build sets `NEXT_STANDALONE=1` and runs
the generated `server.js`; local builds use `next start`. Attachment bytes and LangGraph
checkpoints stay in PostgreSQL; there is no public bucket or attachment URL. The
frontend uses a server-only private API hostname. Only the dashboard is public.

The selected Render plans require payment. Review the current estimate before creating
the Blueprint. The configuration follows the
[Render Blueprint reference](https://render.com/docs/blueprint-spec).

## Local container verification

Local build/startup and `scripts/smoke_containers.py --restart` passed on 2026-09-13
with Gemini disabled. Render configuration passed its published JSON schema. These are
local checks, not a hosted deployment.

Start Docker Desktop. From the repository root, to start without loading `.env` or
enabling Gemini:

```sh
env GEMINI_API_KEY= docker compose --env-file /dev/null -p policy-verify up --build -d --wait
docker compose --env-file /dev/null -p policy-verify ps
uv run python scripts/smoke_containers.py --restart
```

Open http://127.0.0.1:3003. This is a separate PostgreSQL demo; the existing local
SQLite database and servers on 8000/3002 are not used. The migration job must exit
successfully before API and worker start. The API and database have no host ports. Use
sample requests for this rule-based check. To test Gemini deliberately, supply the key
and model through a secure environment and recreate API/worker; never put keys into an
image, build argument, source file, or browser configuration.

Stop containers with `docker compose --env-file /dev/null -p policy-verify down`. The
named database volume survives. Do not add `--volumes` unless intentionally deleting
that demo.

## Migrate an existing local database

This release replaces schema bootstrap with versioned Alembic migrations. Existing
unversioned databases now require one explicit migration. New local databases are
initialized automatically; `SCHEMA_MODE=verify` refuses startup until migrations have
been run.

1. Stop the API and all workers; keep the dashboard closed during maintenance.
2. Back up the database. For SQLite, while stopped, copy `policy_demo.db` and any
   accompanying journal/WAL files. For PostgreSQL, use a verified provider backup or
   `pg_dump` through your secure connection settings.
3. Run the following for the default local SQLite file:

   ```sh
   env DATABASE_URL=sqlite:///./policy_demo.db uv run python -m policy_update.migrate
   ```

4. Restart API and worker and reopen an existing case. Verify its saved proposals,
   evidence, and completed outcome. A replay of an applied version must return its
   original receipt.

The migration command deliberately requires `DATABASE_URL` in the environment; it does
not read `.env`. Never paste a production database password into a shared terminal
transcript. For PostgreSQL use the host's securely injected variable.

Revision `0001` freezes the original schema and adopts known earlier schemas, including
missing nullable request-extraction and worker-lease columns. `0002` adds shared quota
counters and backfills retained case/file usage. The legacy adapter checks required
columns, primary keys, and declared unique constraints. It is not a general
schema-repair tool; review other drift offline. Downgrade is intentionally unsupported:
stop services and restore a verified backup if rollback is needed. Future changes
require a new revision; do not edit revisions already deployed. LangGraph maintains its
own checkpoint schema through its pinned checkpointer.

## Guest lifecycle and limits

Defaults (override consistently on API and worker):

- `GUEST_TTL_SECONDS=604800`: seven days from creation; authentication and worker steps
  refuse expired workspaces. This is an absolute lifetime, not sliding expiry.
- `MAX_WORKSPACES=2000`: retained workspaces across this deployment (Render: 200).
- `MAX_WORKSPACE_CASES=25`, `MAX_CASE_VERSIONS=50`.
- `MAX_WORKSPACE_ATTACHMENT_BYTES=26214400`, `MAX_CASE_ATTACHMENTS=10`.
- `MAX_WORKSPACE_RUNS=50`, `MAX_DAILY_RUNS=200` (Render: 100 queued attempts/day UTC).
- Existing file limit: 5 MiB. API and proxy also bound request bodies before
  buffering/parsing them. Keep the provider's ingress size/concurrency limits enabled.

Limits return 429 and do not save a partially accepted operation. Counters are atomic
and persistent across processes and restarts. Daily run limits count accepted queue
operations, including manual resume/retry, not individual Gemini calls. Each segment has
its own tool budget and automatic stalled-worker retries, so these limits are not a
dollar spending cap. Set provider billing/quota controls too. These are small-demo
safeguards, not protection against every denial-of-service attack.

Cleanup is deliberately offline because LangGraph writes checkpoints through a separate
connection. On a regular maintenance schedule (e.g. weekly), stop API and worker, retain
required backups, and use securely injected `DATABASE_URL`:

```sh
uv run python -m policy_update.cleanup
env MAINTENANCE_MODE=offline uv run python -m policy_update.cleanup --apply
```

The first command prints only the number eligible. The second deletes expired
workspaces, cases, proposals, receipts, attachments, audits, and their checkpoint
threads in one database transaction. Other guests remain. Restore services after
checking the result. Expiry does not itself erase stored records; cleanup must run.

## Render release sequence (owner actions)

1. Review, commit, and push the changes.
2. Connect the repository in Render and review `render.yaml`, region and pricing. Create
   the Blueprint only after approving the displayed paid resources.
3. Enter `GEMINI_API_KEY` in the secure environment group and select a model that your
   key can access. Use the same model and limits for API/worker.
4. Confirm the API pre-deploy migration completes. On the first deployment a worker may
   start before the API migration and fail its schema check; restart it once migration
   succeeds. For later schema changes stop worker/API during maintenance.
5. Confirm the dashboard receives the private API host, `COOKIE_SECURE=true`, and a
   public HTTPS URL. Inspect cookie flags: Secure, HttpOnly, SameSite=Strict. Database
   external IP access is disabled by the Blueprint.
6. Confirm all three GitHub workflows (backend, dashboard, containers) pass on this
   commit. Their presence in the repository alone does not prove a hosted run. Browser
   CI uses synthetic fakes.
7. Complete all twelve acceptance criteria from `plan.md` on the hosted environment.
   Record the URL, commit, date, model, case IDs, and outcomes without credentials.

## Hosted acceptance and recovery checks

- Repeat valid contact/address, missing evidence/reply, conflicting evidence/correction,
  wrong broker, cross-guest case/file denial, rejection, and stale approval scenarios.
- Approve a proposal, then change it: the old version must not execute.
- Leave a case waiting for approval, restart API and worker, then resume that same case.
- Restart a worker during a synthetic run; after its lease lapses, another worker must
  reclaim it or expose a retryable failure. No duplicate policy update is allowed.
- Replay a completed execution version and compare its saved receipt and audit count.
- Confirm expired guests are denied, budgets return safe errors, and file downloads
  remain authenticated with `private, no-store` responses.
- Inspect logs for operational status only. Container API access logging is disabled;
  worker errors record exception classes and sanitized provider categories. Never export
  tokens, request contents, document bytes, or database credentials.

Do not mark V08 complete until these hosted checks actually pass.
