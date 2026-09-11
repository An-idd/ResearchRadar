import asyncio
import sys

from alembic import context
from sqlalchemy import Connection

from app.config import get_settings
from app.storage.database import make_engine
from app.storage.models import Base


def run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online() -> None:
    settings = get_settings()
    direct_url = settings.database_url_unpooled.get_secret_value()
    if not direct_url:
        raise ValueError("DATABASE_URL_UNPOOLED is required for migrations")
    engine = make_engine(direct_url)
    async with engine.connect() as connection:
        await connection.run_sync(run)
    await engine.dispose()


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(online())
