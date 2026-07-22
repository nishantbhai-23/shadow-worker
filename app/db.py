from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings

# statement_cache_size=0 disables asyncpg's server-side prepared-statement cache, which
# conflicts with Neon's pooled (PgBouncer transaction-mode) endpoint -- without this,
# queries after the first can fail with "prepared statement ... does not exist" once
# PgBouncer routes a later query to a different backend connection.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session
