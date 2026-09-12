from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def now() -> str:
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[str] = mapped_column(default=now)


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("workspace_id", "number"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    number: Mapped[str]
    holder_name: Mapped[str]
    mailing_address: Mapped[str]
    email: Mapped[str]
    phone: Mapped[str]
    revision: Mapped[int] = mapped_column(default=1)

    __mapper_args__ = {"version_id_col": revision}


class Assignment(Base):
    __tablename__ = "assignments"

    policy_id: Mapped[str] = mapped_column(ForeignKey("policies.id"), primary_key=True)
    broker_id: Mapped[str] = mapped_column(primary_key=True)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    broker_id: Mapped[str]
    policy_number: Mapped[str | None]
    original_request: Mapped[str]
    replies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    evidence_id: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="processing")
    current_version: Mapped[int] = mapped_column(default=0)
    follow_up: Mapped[str | None]
    confirmation: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)
    revision: Mapped[int] = mapped_column(default=1)

    __mapper_args__ = {"version_id_col": revision}


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (UniqueConstraint("case_id", "version"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    version: Mapped[int]
    changes: Mapped[dict[str, str]] = mapped_column(JSON)
    before: Mapped[dict[str, str]] = mapped_column(JSON)
    policy_revision: Mapped[int | None]
    findings: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str]
    approved_by: Mapped[str | None]
    approved_at: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)


class Execution(Base):
    __tablename__ = "executions"

    # The proposal ID is the stable idempotency key, enforced by the database.
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), primary_key=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    actor: Mapped[str]
    action: Mapped[str]
    proposal_version: Mapped[int | None]
    details: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)
