from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
    )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    # close() rolls back the read-only transaction and returns its connection.
    async with request.app.state.sessions() as session:
        yield session
