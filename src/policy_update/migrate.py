"""Explicit one-shot migration command; requires DATABASE_URL in the environment."""

import os

from policy_update.database import make_database, upgrade_database


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL explicitly; this command does not read .env")
    engine, _ = make_database(url)
    try:
        upgrade_database(engine)
    except Exception as error:
        raise SystemExit(
            f"Migration failed ({type(error).__name__}); inspect schema offline"
        ) from None
    finally:
        engine.dispose()
    print("Database migrations complete")


if __name__ == "__main__":
    main()
