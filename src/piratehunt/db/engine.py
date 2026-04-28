from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from piratehunt.config import settings


def _async_database_url(database_url: str) -> str:
    """Convert a SQLAlchemy URL to its asyncpg variant when needed."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


engine = create_async_engine(_async_database_url(settings.database_url), pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an async SQLAlchemy session for FastAPI dependencies."""
    async with async_session_maker() as session:
        yield session


async def close_engine() -> None:
    """Close the SQLAlchemy engine pool."""
    await engine.dispose()
