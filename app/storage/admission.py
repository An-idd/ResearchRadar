"""Persistence for small, content-free admission decisions."""

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import AdmissionRecord, utcnow


class AdmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> AdmissionRecord | None:
        return await self.session.get(AdmissionRecord, key)

    async def save(self, values: dict[str, Any]) -> None:
        values = {**values, "updated_at": utcnow()}
        stmt = insert(AdmissionRecord).values(**values)
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=["key"],
                set_={k: v for k, v in values.items() if k != "key"},
                # A late failure/defer must not overwrite a concurrent completed decision.
                where=AdmissionRecord.status.in_(["failed", "deferred"]),
            )
        )
