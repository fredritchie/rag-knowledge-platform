from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from rag_platform.config import DatabaseSettings


class Database:
    def __init__(self, config: DatabaseSettings):
        kwargs: dict[str, object] = {"echo": config.echo, "pool_pre_ping": True}
        if not config.url.startswith("sqlite"):
            kwargs.update(
                pool_size=config.pool_size,
                max_overflow=config.max_overflow,
                pool_timeout=config.pool_timeout_seconds,
            )
        self.engine: AsyncEngine = create_async_engine(config.url, **kwargs)
        self.sessions = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self.engine.dispose()
