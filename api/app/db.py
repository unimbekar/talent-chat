"""Database engines. Public routes use the app_public role."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_admin_engine = None
_public_engine = None
_admin_factory = None
_public_factory = None


def admin_engine():
    global _admin_engine, _admin_factory
    if _admin_engine is None:
        _admin_engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        _admin_factory = sessionmaker(bind=_admin_engine, expire_on_commit=False)
    return _admin_engine


def public_engine():
    global _public_engine, _public_factory
    if _public_engine is None:
        _public_engine = create_engine(get_settings().database_public_url, pool_pre_ping=True)
        _public_factory = sessionmaker(bind=_public_engine, expire_on_commit=False)
    return _public_engine


def admin_session() -> Session:
    admin_engine()
    return _admin_factory()


def public_session() -> Session:
    public_engine()
    return _public_factory()


def get_admin_db() -> Iterator[Session]:
    session = admin_session()
    try:
        yield session
    finally:
        session.close()


def get_public_db() -> Iterator[Session]:
    session = public_session()
    try:
        yield session
    finally:
        session.close()


def reset_engines() -> None:
    global _admin_engine, _public_engine, _admin_factory, _public_factory
    if _admin_engine is not None:
        _admin_engine.dispose()
    if _public_engine is not None:
        _public_engine.dispose()
    _admin_engine = None
    _public_engine = None
    _admin_factory = None
    _public_factory = None
