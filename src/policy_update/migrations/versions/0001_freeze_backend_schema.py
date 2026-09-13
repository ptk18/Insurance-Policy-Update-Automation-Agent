"""Freeze the backend schema and adopt known unversioned demo databases."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# Frozen baseline, independent of future application metadata. Known nullable
# additions adopt pre-migration demo databases without deleting their records.
metadata = sa.MetaData()
NULLABLE_ADDITIONS = {
    "cases": {"requested_changes"},
    "processing_jobs": {"queued_at", "worker_id", "lease_expires_at"},
}


def _table(name, *items):
    table = sa.Table(name, metadata, *items, extend_existing=True)
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table(name):
        table.create(connection)
        return
    columns = {c["name"] for c in inspector.get_columns(name)}
    for column in table.columns:
        if column.name not in columns:
            if column.name not in NULLABLE_ADDITIONS.get(name, set()):
                raise RuntimeError(f"Unsupported legacy schema: {name}.{column.name} missing")
            op.add_column(name, sa.Column(column.name, column.type, nullable=True))
    primary = set(inspector.get_pk_constraint(name)["constrained_columns"])
    if primary != {c.name for c in table.primary_key.columns}:
        raise RuntimeError(f"Unsupported legacy primary key: {name}")
    unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(name)}
    for constraint in table.constraints:
        if isinstance(constraint, sa.UniqueConstraint):
            if tuple(c.name for c in constraint.columns) not in unique:
                raise RuntimeError(f"Unsupported legacy unique constraint: {name}")


def _index(name, table_name, columns, unique=False):
    sa.Index(name, *(metadata.tables[table_name].c[c] for c in columns), unique=unique).create(
        op.get_bind(), checkfirst=True
    )


def upgrade():
    metadata.clear()
    _table(
        "workspaces",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    _table(
        "cases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("broker_id", sa.String(), nullable=False),
        sa.Column("policy_number", sa.String(), nullable=True),
        sa.Column("original_request", sa.String(), nullable=False),
        sa.Column("replies", sa.JSON(), nullable=False),
        sa.Column("evidence_id", sa.String(), nullable=True),
        sa.Column("requested_changes", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("follow_up", sa.String(), nullable=True),
        sa.Column("confirmation", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_cases_workspace_id", "cases", ["workspace_id"], unique=False)

    _table(
        "policies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("number", sa.String(), nullable=False),
        sa.Column("holder_name", sa.String(), nullable=False),
        sa.Column("mailing_address", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "number"),
    )
    _index("ix_policies_workspace_id", "policies", ["workspace_id"], unique=False)

    _table(
        "assignments",
        sa.Column("policy_id", sa.String(), nullable=False),
        sa.Column("broker_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["policies.id"],
        ),
        sa.PrimaryKeyConstraint("policy_id", "broker_id"),
    )
    _table(
        "attachments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(length=120), nullable=False),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("inspection", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_attachments_case_id", "attachments", ["case_id"], unique=False)
    _index("ix_attachments_workspace_id", "attachments", ["workspace_id"], unique=False)

    _table(
        "audit_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("proposal_version", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _index("ix_audit_events_case_id", "audit_events", ["case_id"], unique=False)

    _table(
        "processing_jobs",
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("queued_at", sa.String(), nullable=True),
        sa.Column("worker_id", sa.String(), nullable=True),
        sa.Column("lease_expires_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.PrimaryKeyConstraint("case_id"),
    )
    _index("ix_processing_jobs_status", "processing_jobs", ["status"], unique=False)
    _index("ix_processing_jobs_workspace_id", "processing_jobs", ["workspace_id"], unique=False)

    _table(
        "proposals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("policy_revision", sa.Integer(), nullable=True),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "version"),
    )
    _index("ix_proposals_case_id", "proposals", ["case_id"], unique=False)

    _table(
        "executions",
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
        ),
        sa.PrimaryKeyConstraint("proposal_id"),
    )


def downgrade():
    raise RuntimeError("Restore a verified backup instead of deleting demo records")
