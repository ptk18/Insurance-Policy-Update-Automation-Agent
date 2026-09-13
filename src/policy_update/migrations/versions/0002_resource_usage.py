"""Shared public-demo quotas, including retained pre-migration records."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "resource_usage",
        sa.Column("key", sa.String(160), primary_key=True),
        sa.Column("amount", sa.Integer(), nullable=False),
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO resource_usage (key, amount) SELECT 'workspaces', count(*) FROM workspaces"
        )
    )
    for prefix, table, expression in (
        ("cases", "cases", "count(*)"),
        ("bytes", "attachments", "sum(size)"),
        ("runs", "processing_jobs", "sum(attempts)"),
    ):
        connection.execute(
            sa.text(
                f"INSERT INTO resource_usage (key, amount) "
                f"SELECT '{prefix}:' || workspace_id, {expression} "
                f"FROM {table} GROUP BY workspace_id"
            )
        )
    connection.execute(
        sa.text(
            "INSERT INTO resource_usage (key, amount) "
            "SELECT 'files:' || case_id, count(*) FROM attachments GROUP BY case_id"
        )
    )


def downgrade():
    raise RuntimeError("Restore a verified backup instead of removing usage limits")
