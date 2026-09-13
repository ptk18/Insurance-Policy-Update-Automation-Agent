"""Offline guest cleanup. Default is a count-only preview; --apply needs maintenance mode.

Stop API and workers before --apply: checkpoint writes use independent connections.
Application records and checkpoints are deleted in one database transaction.
"""

import argparse
import os

from sqlalchemy import MetaData, Table, delete, func, inspect, select, update

from policy_update.database import make_database, require_current_schema
from policy_update.limits import expiry_cutoff
from policy_update.models import (
    Assignment,
    Attachment,
    AuditEvent,
    Case,
    Execution,
    Policy,
    ProcessingJob,
    Proposal,
    ResourceUsage,
    Workspace,
)


def expired_workspaces(session):
    return list(
        session.scalars(select(Workspace.id).where(Workspace.created_at <= expiry_cutoff()))
    )


def purge_expired(session):
    """Maintenance-only operation; caller must stop services first."""
    owners = expired_workspaces(session)
    tables = set(inspect(session.connection()).get_table_names())
    for owner in owners:
        ids = list(session.scalars(select(Case.id).where(Case.workspace_id == owner)))
        for name in ("checkpoint_writes", "writes", "checkpoint_blobs", "checkpoints"):
            if name in tables:
                table = Table(name, MetaData(), autoload_with=session.connection())
                session.execute(delete(table).where(table.c.thread_id.in_(ids)))
        proposals = select(Proposal.id).where(Proposal.case_id.in_(ids))
        session.execute(delete(Execution).where(Execution.proposal_id.in_(proposals)))
        for model in (AuditEvent, Proposal, Attachment, ProcessingJob):
            session.execute(delete(model).where(model.case_id.in_(ids)))
        session.execute(delete(Case).where(Case.workspace_id == owner))
        policies = select(Policy.id).where(Policy.workspace_id == owner)
        session.execute(delete(Assignment).where(Assignment.policy_id.in_(policies)))
        session.execute(delete(Policy).where(Policy.workspace_id == owner))
        keys = [f"{prefix}:{owner}" for prefix in ("cases", "bytes", "runs")]
        keys.extend(f"files:{case_id}" for case_id in ids)
        session.execute(delete(ResourceUsage).where(ResourceUsage.key.in_(keys)))
        session.execute(delete(Workspace).where(Workspace.id == owner))
    # Recount while services are stopped; old global daily budgets hold no guest data.
    session.execute(
        update(ResourceUsage)
        .where(ResourceUsage.key == "workspaces")
        .values(amount=session.scalar(select(func.count()).select_from(Workspace)))
    )
    return len(owners)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and os.environ.get("MAINTENANCE_MODE") != "offline":
        raise SystemExit("Stop API/workers, then set MAINTENANCE_MODE=offline to apply cleanup")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL explicitly; this command does not read .env")
    engine, sessions = make_database(url)
    try:
        require_current_schema(engine)
        with sessions.begin() as session:
            count = purge_expired(session) if args.apply else len(expired_workspaces(session))
        print(f"Expired workspaces {'deleted' if args.apply else 'eligible'}: {count}")
    except Exception as error:
        raise SystemExit(f"Cleanup failed ({type(error).__name__}); no details logged") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
