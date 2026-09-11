import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.storage.database import database_url


def test_uvicorn_database_loop() -> None:
    import asyncio

    import uvicorn

    factory = uvicorn.Config(
        create_app(Settings()), loop="app.cli:database_loop_factory"
    ).get_loop_factory()
    assert factory
    loop = factory()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()


async def test_health_without_database() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        assert (await client.get("/health")).json() == {"status": "ok"}


def test_config_and_url() -> None:
    with pytest.raises(ValidationError):
        Settings(summary_budget=-1)
    with pytest.raises(ValueError):
        database_url("sqlite:///test.db")
    url = database_url("postgresql://u:p@host/db?sslmode=require&channel_binding=require")
    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"
    assert "password" not in repr(Settings(database_url="postgresql://user:password@host/db"))
