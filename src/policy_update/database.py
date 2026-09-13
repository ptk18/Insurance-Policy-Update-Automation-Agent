import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def make_database(url: str):
    url = normalize_url(url)
    options = {}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 15}
        if url.endswith(":memory:"):
            options["poolclass"] = StaticPool
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True, **options)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine, sessionmaker(engine, expire_on_commit=False)


def normalize_url(url: str) -> str:
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def migration_config(connection=None):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
    config.attributes["connection"] = connection
    return config


def upgrade_database(engine):
    """Explicit migration entry point. Never prints connection strings or data."""
    with engine.begin() as connection:
        command.upgrade(migration_config(connection), "head")


def require_current_schema(engine):
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_heads()
    expected = tuple(ScriptDirectory.from_config(migration_config()).get_heads())
    if current != expected:
        raise RuntimeError("Database upgrade required: run python -m policy_update.migrate")


def initialize_database(engine):
    # Only new local databases auto-migrate; existing schemas require explicit maintenance.
    if os.environ.get("SCHEMA_MODE", "local") == "local" and not inspect(engine).has_table(
        "workspaces"
    ):
        upgrade_database(engine)
    require_current_schema(engine)
