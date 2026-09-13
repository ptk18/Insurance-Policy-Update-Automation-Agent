"""Use an injected connection for tests/startup; CLI reads DATABASE_URL, never .env."""

import os

from alembic import context
from sqlalchemy import create_engine

from policy_update.database import normalize_url
from policy_update.models import Base


def run(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL explicitly before running migrations")
    engine = create_engine(normalize_url(url), hide_parameters=True)
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
