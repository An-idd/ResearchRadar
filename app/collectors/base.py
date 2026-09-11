from datetime import datetime
from typing import Protocol

from app.domain import RawPaper


class PaperCollector(Protocol):
    source: str

    async def collect(self, since: datetime, until: datetime) -> list[RawPaper]: ...
