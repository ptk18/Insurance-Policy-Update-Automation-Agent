from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from policy_update.models import Base


def make_database(url: str):
    options = {}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 15}
        if url.endswith(":memory:"):
            options["poolclass"] = StaticPool
    engine = create_engine(url, **options)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine, sessionmaker(engine, expire_on_commit=False)


def initialize_database(engine):
    # Bootstrap only. Replace with versioned migrations before deploying shared data.
    Base.metadata.create_all(engine)
    add_missing_columns(engine)


def add_missing_columns(engine):
    """Add nullable columns and indexes that a table created by an earlier bootstrap
    lacks, so a local database file keeps working across schema additions without
    being reset. Nullable additions only: anything else needs a real migration (V05).
    Run it from one process at a time (the API owns bootstrap; the worker waits)."""
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or not column.nullable:
                    continue
                column_type = column.type.compile(engine.dialect)
                connection.execute(
                    text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {column_type}')
                )
            for index in table.indexes:
                index.create(connection, checkfirst=True)
