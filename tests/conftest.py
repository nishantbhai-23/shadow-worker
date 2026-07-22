import os

# Must happen before any `app.*` import: app.config.settings is built at import time
# and several required fields have no defaults.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test-token")
os.environ.setdefault("TELEGRAM_START_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("LLM_API_KEY", "test-key")

import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402
from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: E402

import app.models  # noqa: E402,F401  (registers tables on SQLModel.metadata)


@pytest_asyncio.fixture
async def session_maker():
    """A fresh in-memory SQLite DB per test. StaticPool keeps it alive across the
    multiple connections SQLAlchemy's async pool would otherwise open, which would
    each see a *different* empty :memory: database."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture
async def session(session_maker):
    async with session_maker() as s:
        yield s
