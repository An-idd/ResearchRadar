import asyncio
import os
import sys
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Settings
from app.storage.database import make_engine, sessions


def pytest_configure() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    settings = Settings(_env_file=os.getenv("RADAR_TEST_ENV_FILE", ".env.test"))
    if settings.neon_branch != "mvp-test":
        pytest.fail("Database tests require NEON_BRANCH=mvp-test; never use production")
    url = settings.database_url.get_secret_value()
    if not url:
        pytest.fail("Configure .env.test with the dedicated Neon mvp-test database")
    for path in (".env", ".env.development", ".env.local"):
        other = Settings(_env_file=path).database_url.get_secret_value()
        if other and (make_url(other).host or "").replace("-pooler", "") == (
            make_url(url).host or ""
        ).replace("-pooler", ""):
            pytest.fail("Test and application database URLs must differ")
    engine = make_engine(url)
    async with engine.begin() as connection:
        rows = await connection.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename != 'alembic_version'"
            )
        )
        names = [row[0] for row in rows]
        if names:
            from app.storage.models import Base

            if set(names) - set(Base.metadata.tables):
                pytest.fail("Refusing to clear unknown tables")
            await connection.execute(
                text("TRUNCATE " + ",".join('"' + name + '"' for name in names) + " CASCADE")
            )
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with sessions(db_engine)() as value:
        yield value
