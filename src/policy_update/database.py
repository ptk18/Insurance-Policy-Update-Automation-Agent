from sqlalchemy import create_engine, event
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
