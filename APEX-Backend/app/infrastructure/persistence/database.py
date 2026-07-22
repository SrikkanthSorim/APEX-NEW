"""SQLAlchemy database engine and session setup.

For a Java developer: `engine` is roughly a JDBC DataSource/connection pool.
`SessionLocal` is a session factory, similar to a Hibernate `SessionFactory`
or a JPA `EntityManagerFactory`. Each HTTP request gets its own `Session`
(like a Hibernate `Session`/JPA `EntityManager`) via the `get_db()`
dependency below — FastAPI creates one per request and closes it afterward.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

# `pool_pre_ping=True` makes SQLAlchemy validate a pooled connection with a
# cheap "SELECT 1" before handing it to a request, so a connection the
# database silently closed (e.g. after being idle) is transparently replaced
# instead of surfacing as a request-time error.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# Factory for `Session` objects — comparable to Hibernate's `SessionFactory`.
# `autoflush=False`/`autocommit=False` are the SQLAlchemy 2.0 defaults,
# listed explicitly here for clarity.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class every ORM model inherits from.

    `app.infrastructure.persistence.models` defines the actual tables
    (`User`, `RefreshToken`, ...) as subclasses of this `Base`.
    """


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields one database session per request.

    FastAPI calls this as a generator: the code before `yield` runs before
    the route handler, and the code after `yield` always runs afterward
    (even if the handler raised) — similar to a try/finally wrapped around a
    Hibernate session. Use it as `db: Session = Depends(get_db)`.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # A route handler raised without committing/rolling back itself —
        # make sure the failed transaction never leaks into the next use of
        # this connection.
        db.rollback()
        raise
    finally:
        db.close()


def _quote_identifier(name: str) -> str:
    """Safely quote a Postgres identifier (e.g. a database name) for use
    inside a DDL statement, where SQLAlchemy's normal `:param` bind
    placeholders don't work (CREATE DATABASE doesn't accept parameters).
    Doubling embedded double-quotes is Postgres's own escaping rule for
    quoted identifiers.
    """
    return '"' + name.replace('"', '""') + '"'


def ensure_database_exists() -> None:
    """Create the target PostgreSQL database if it doesn't exist yet.

    A fresh PostgreSQL install always has a default `postgres` maintenance
    database — this connects there (never to the target database, which may
    not exist yet) and issues `CREATE DATABASE` if needed. This is a local/
    dev convenience: it does NOT create the PostgreSQL user/role itself, and
    the connecting user still needs the `CREATEDB` privilege (true by
    default for a superuser like `postgres`).

    Called once at startup, before `verify_database_connection()` — see
    `app/main.py`.
    """
    target_url = make_url(settings.database_url)
    target_db_name = target_url.database
    if not target_db_name:
        # Nothing to create against — let verify_database_connection()
        # produce its usual clear error instead.
        return

    # `postgres` is the standard always-present maintenance database used
    # for admin operations like CREATE DATABASE — the same trick `createdb`
    # the CLI tool uses under the hood.
    maintenance_url = target_url.set(database="postgres")

    # CREATE DATABASE cannot run inside a transaction block in PostgreSQL,
    # so this connection must use autocommit rather than SQLAlchemy's
    # default (implicit transaction per statement).
    maintenance_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with maintenance_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target_db_name},
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(text(f"CREATE DATABASE {_quote_identifier(target_db_name)}"))
                logger.info("Database '%s' did not exist — created it.", target_db_name)
    except Exception as exc:
        logger.error("Could not verify/create database '%s': %s", target_db_name, type(exc).__name__)
        raise RuntimeError(
            f"Could not connect to PostgreSQL to check/create the '{target_db_name}' database. "
            "Check DATABASE_URL's host/port/username/password in APEX-Backend/.env, confirm "
            "PostgreSQL is running, and confirm that user has the CREATEDB privilege."
        ) from exc
    finally:
        maintenance_engine.dispose()


def verify_database_connection() -> None:
    """Fail fast with a clear error if the database is unreachable.

    Called once at application startup (see `app/main.py`) so a
    misconfigured DATABASE_URL or a stopped PostgreSQL service produces an
    obvious startup error instead of a confusing failure on the first
    request.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Database connection failed at startup: %s", type(exc).__name__)
        raise RuntimeError(
            "Could not connect to the database. Check DATABASE_URL in "
            "APEX-Backend/.env and confirm PostgreSQL is running."
        ) from exc
