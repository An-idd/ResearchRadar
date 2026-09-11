from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def database_url(value: str) -> URL:
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        raise ValueError("ResearchRadar requires PostgreSQL")
    return url.set(drivername="postgresql+psycopg")


def make_engine(value: str) -> AsyncEngine:
    return create_async_engine(
        database_url(value),
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        connect_args={"prepare_threshold": None, "connect_timeout": 15},
    )


def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
