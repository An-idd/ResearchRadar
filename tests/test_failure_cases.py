import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.collectors.huggingface import HuggingFaceCollector
from app.collectors.openreview import OpenReviewCollector
from app.config import Settings
from app.domain import Classification, RawPaper, TopicMatch
from app.intelligence.service import IntelligenceService
from app.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from app.providers.http import request
from app.storage.database import sessions
from app.storage.intelligence import IntelligenceRepository
from app.storage.models import Paper, PaperSourceRecord, PaperSummaryRecord
from app.storage.repository import PaperRepository
from app.topics import load_taxonomy


async def test_http_timeout_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.http.asyncio.sleep", AsyncMock())
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if len(calls) < 3:
            raise httpx.ReadTimeout("transient")
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await request(client, "GET", "https://example.org")).status_code == 200
    assert len(calls) == 3


async def test_hf_newest_date_first_and_openreview_empty() -> None:
    days = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "huggingface" in req.url.host:
            days.append(req.url.params["date"])
            return httpx.Response(200, json=[])
        assert req.url.params["content.venueid"] == "ICLR.cc/2026/Conference"
        return httpx.Response(200, json={"notes": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        start, end = datetime(2026, 9, 9, tzinfo=UTC), datetime(2026, 9, 11, tzinfo=UTC)
        assert await HuggingFaceCollector(client).collect(start, end) == []
        assert days == ["2026-09-10", "2026-09-09"]
        assert (
            await OpenReviewCollector(client, "ICLR.cc/2026/Conference").collect(start, end) == []
        )


@pytest.mark.integration
async def test_concurrent_ingestion_and_embedding_fallback(db_engine: AsyncEngine) -> None:
    factory = sessions(db_engine)
    now = datetime.now(UTC)
    raw = RawPaper(
        source="fixture",
        source_id="1",
        title="A memory selection policy",
        published_at=now,
        paper_url="https://arxiv.org/abs/2609.00001",
    )

    async def ingest() -> object:
        async with factory() as session, session.begin():
            return (await PaperRepository(session).ingest(raw, now, [1.0] + [0.0] * 383, "test")).id

    one, two = await asyncio.gather(ingest(), ingest())
    assert one == two
    async with factory() as session, session.begin():
        other = raw.model_copy(update={"source_id": "2", "title": "Learned persistent memory"})
        merged = await PaperRepository(session).ingest(other, now, [1.0] + [0.0] * 383, "test")
        assert merged.id == one
        assert await session.scalar(select(func.count()).select_from(Paper)) == 1
        review = raw.model_copy(update={"source_id": "3", "title": "Memory controller variant"})
        review_vector = [0.93, (1 - 0.93**2) ** 0.5] + [0.0] * 382
        separate = await PaperRepository(session).ingest(review, now, review_vector, "test")
        assert separate.id != one
        record = await session.scalar(
            select(PaperSourceRecord).where(PaperSourceRecord.source_id == "3")
        )
        assert record and record.payload["metadata"]["potential_duplicates"][0]["paper_id"] == str(
            one
        )

    from test_end_to_end import FixtureCollector

    from app.papers.ingestion import IngestionService

    class BrokenEmbedding:
        model = "unavailable"

        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("model unavailable")

    results = await IngestionService(factory, BrokenEmbedding()).collect(
        [FixtureCollector()], now - timedelta(days=7), now
    )
    assert results["fixture"]["status"] == "partial"
    assert results["fixture"]["count"] == 2


@pytest.mark.integration
async def test_prior_excludes_future_and_bad_evidence_never_persists(
    db_engine: AsyncEngine,
) -> None:
    from test_end_to_end import responder

    from app.domain import PaperSummary

    factory = sessions(db_engine)
    topics = load_taxonomy(Path("config/taxonomy.json"))
    now = datetime(2026, 9, 11, tzinfo=UTC)
    papers = []
    async with factory() as session, session.begin():
        repo = IntelligenceRepository(session)
        await repo.sync_topics(topics)
        for i in range(3):
            raw = RawPaper(
                source="arxiv",
                source_id=f"2609.0000{i}",
                arxiv_id=f"2609.0000{i}",
                title=f"Agent memory {i}",
                abstract="A learned memory policy.",
                published_at=now + timedelta(days=i - 1),
                paper_url=f"https://arxiv.org/abs/2609.0000{i}",
                pdf_url=f"https://arxiv.org/pdf/2609.0000{i}",
            )
            paper = await PaperRepository(session).ingest(
                raw, now, [1.0] + [0.0] * 383, "fixture-embedding-v1"
            )
            await repo.set_topics(
                paper.id, Classification(topics=[TopicMatch(slug="agent", confidence=1)])
            )
            papers.append(paper)
    async with factory() as session:
        priors = await IntelligenceRepository(session).prior_papers(papers[1])
        assert [p.id for p in priors] == [papers[0].id]

    def invalid(prompt: list, schema: type) -> dict:
        output = responder(prompt, schema)
        if schema is PaperSummary:
            output["evidence"][0]["quote"] = "This quote never existed"
        return output

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(404))
    ) as client:
        service = IntelligenceService(
            factory,
            FakeLLMProvider(invalid),
            FakeEmbeddingProvider(),
            client,
            Settings(fulltext_enabled=True),
            topics,
        )
        fallback = await service.source(papers[1])
        assert fallback.scope == "abstract-only"
        with pytest.raises(ValueError, match="evidence"):
            await service.analyze(papers[1].id)
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(PaperSummaryRecord)) == 0
