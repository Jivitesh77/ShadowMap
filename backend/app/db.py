"""Database connection. SQLite file + SQLAlchemy."""

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app import config


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Current time in UTC. Stored without timezone because SQLite does not keep it; all times are UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


def make_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")  # enforce links between tables
            cur.execute("PRAGMA journal_mode=WAL")  # lets readers and writers work at the same time
            cur.close()
    return engine


engine = make_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(bind: Engine = engine) -> None:
    from app import models  # noqa: F401  (registers the tables)

    Base.metadata.create_all(bind)
    _add_missing_columns(bind)
    _create_missing_indexes(bind)
    _label_unlabelled_city_rows(bind)
    _fill_walk_versions(bind)


def _label_unlabelled_city_rows(bind: Engine) -> None:
    """Rows from before multi-city support belong to the original pilot. Only fills empty labels; changes nothing else."""
    with bind.begin() as conn:
        for table in ("streets", "places", "video_jobs", "walks"):
            conn.execute(text(f"UPDATE {table} SET city = 'guwahati' WHERE city IS NULL"))


def _fill_walk_versions(bind: Engine) -> None:
    """Walks from before optimistic locking get version 1 (a NULL version could never be updated)."""
    with bind.begin() as conn:
        conn.execute(text("UPDATE walks SET version = 1 WHERE version IS NULL"))


def _create_missing_indexes(bind: Engine) -> None:
    """create_all makes indexes only for new tables, and _add_missing_columns adds bare columns. Create every index the
    models declare that the database lacks (CREATE INDEX IF NOT EXISTS: never drops or rewrites anything)."""
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(conn, checkfirst=True)


def _add_missing_columns(bind: Engine) -> None:
    """Small safe upgrade: add columns that newer code expects to existing tables. Never drops or changes data.
    New columns must therefore allow empty values (nullable)."""
    insp = inspect(bind)
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    if not col.nullable:
                        raise RuntimeError(f"Column {table.name}.{col.name} must be nullable to be added automatically.")
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(bind.dialect)}'))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
