from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import RawPaper
from app.papers.normalize import normalize_arxiv, normalize_doi, normalize_title
from app.storage.models import Paper, PaperSourceRecord
from app.storage.repository import PaperRepository


def sample(**updates: object) -> RawPaper:
    return RawPaper.model_validate(
        {
            "source": "arxiv",
            "source_id": "2609.00001v1",
            "arxiv_id": "2609.00001v1",
            "title": "Agent Memory: A Method!",
            "published_at": "2026-09-10T00:00:00Z",
            "paper_url": "https://arxiv.org/abs/2609.00001",
            **updates,
        }
    )


def test_normalization() -> None:
    assert normalize_title("Ａgent—Memory!  ") == "agent memory"
    assert normalize_doi("https://doi.org/10.1234/ABC") == "10.1234/abc"
    assert normalize_arxiv("https://arxiv.org/pdf/2609.00001v2.pdf") == "2609.00001"


@pytest.mark.integration
async def test_dedup_preserves_sources_and_strong_conflicts(session: AsyncSession) -> None:
    repo = PaperRepository(session)
    now = datetime.now(UTC)
    first = await repo.ingest(sample(), now)
    await session.commit()
    merged = await repo.ingest(
        sample(source="openreview", source_id="review-1", arxiv_id=None, doi="10.1234/test"), now
    )
    assert merged.id == first.id
    await session.commit()
    await repo.ingest(sample(), now)
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(PaperSourceRecord)) == 2
    different = await repo.ingest(sample(source_id="2609.00002", arxiv_id="2609.00002"), now)
    assert different.id != first.id
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(Paper)) == 2
