"""Persisted demo budgets and guest expiry, shared by API and worker processes."""

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from policy_update.models import ResourceUsage, Workspace


def setting(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def expiry_cutoff() -> str:
    return (datetime.now(UTC) - timedelta(seconds=setting("GUEST_TTL_SECONDS", 604800))).isoformat()


def require_active(session, workspace_id: str):
    from policy_update.service import DomainError

    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.created_at <= expiry_cutoff():
        raise DomainError(401, "This demo workspace has expired; open a new workspace")
    return workspace


def consume(session, key: str, maximum: int, amount: int = 1):
    """Reserve in the caller's transaction; a rejected write rolls the budget back.

    Conditional UPDATE avoids oversubscription even across independent processes.
    Run reservations take the workspace counter before the global daily counter.
    """
    from policy_update.service import DomainError

    insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
    session.execute(insert(ResourceUsage).values(key=key, amount=0).on_conflict_do_nothing())
    changed = session.execute(
        update(ResourceUsage)
        .where(ResourceUsage.key == key, ResourceUsage.amount + amount <= maximum)
        .values(amount=ResourceUsage.amount + amount)
        .execution_options(synchronize_session=False)
    ).rowcount
    if changed != 1:
        raise DomainError(429, "Demo usage limit reached; try later or contact the demo owner")


def reserve_run(session, workspace_id):
    require_active(session, workspace_id)
    consume(session, f"runs:{workspace_id}", setting("MAX_WORKSPACE_RUNS", 50))
    day = datetime.now(UTC).date().isoformat()
    consume(session, f"daily-runs:{day}", setting("MAX_DAILY_RUNS", 200))
