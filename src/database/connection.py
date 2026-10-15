"""Database connection and session lifecycle management."""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import get_settings
from src.database.models import Base
from src.utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)

# Engine initialization
settings = get_settings()

if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        echo=False,
    )

SessionFactory = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Provide a transactional database session scope with automatic rollback."""
    session: Session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Database transaction rolled back due to error: %s", exc, exc_info=True)
        raise DatabaseError(f"Database transaction failed: {exc}") from exc
    finally:
        session.close()


@contextmanager
def get_read_only_session() -> Generator[Session, None, None]:
    """Provide a read-only session scope for analytics queries and GenAI tools."""
    session: Session = SessionFactory()
    try:
        # PostgreSQL read-only transaction guarantee
        try:
            session.execute(text("SET TRANSACTION READ ONLY"))
        except Exception:
            pass  # Non-PostgreSQL dialect or test SQLite fallback
        yield session
    except Exception as exc:
        logger.error("Read-only query session failed: %s", exc)
        raise DatabaseError(f"Read-only query failed: {exc}") from exc
    finally:
        session.close()


def init_db() -> None:
    """Create all defined database tables idempotently."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully.")
    except Exception as exc:
        logger.error("Database schema initialization failed: %s", exc)
        raise DatabaseError(f"Failed to create schema: {exc}") from exc


def check_db_connection() -> bool:
    """Check connectivity to database and auto-initialize tables for SQLite."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        if settings.DATABASE_URL.startswith("sqlite"):
            init_db()
        return True
    except Exception as exc:
        logger.warning("Database connectivity check failed: %s", exc)
        return False
