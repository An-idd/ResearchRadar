"""Admission must exclude unrelated/unknown content without losing accepted provenance."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain import RawPaper
from app.papers.admission import AdmissionService, retryable_error
from app.papers.ingestion import IngestionService
from app.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from app.storage.database import sessions
from app.storage.models import (
    AdmissionRecord,
    GenerationRecord,
    Paper,
    PaperMetric,
    PaperSourceRecord,
    PaperTopic,
)
from app.topics import load_taxonomy

NOW = datetime(2026, 9, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "error,expected",
    [
        ("TimeoutError", True),
        ("ReadTimeout", True),
        ("HTTP429", True),
        ("HTTP503", True),
        ("HTTP400", False),
        ("HTTP401", False),
        ("HTTP403", False),
        ("ValidationError", False),
        ("ValueError", False),
        ("ProviderError", False),
        (None, False),
    ],
)
def test_retry_only_transient_admission_errors(error: str | None, expected: bool) -> None:
    assert retryable_error(error) is expected


def paper(index: int, title: str) -> RawPaper:
    return RawPaper(
        source="fixture",
        source_id=str(index),
        arxiv_id=f"2609.{index:05d}",
        title=title,
        abstract="Source material.",
        published_at=NOW - timedelta(days=1),
        paper_url=f"https://arxiv.org/abs/2609.{index:05d}",
        metrics={"hf_upvotes": 1},
    )


class Collector:
    def __init__(self, papers: list[RawPaper], source: str = "fixture") -> None:
        self.papers, self.source = papers, source

    async def collect(self, since: datetime, until: datetime) -> list[RawPaper]:
        return self.papers


@pytest.mark.integration
async def test_admission_filters_failures_budget_cache_and_retry(db_engine: AsyncEngine) -> None:
    factory = sessions(db_engine)
    topics = load_taxonomy(Path("config/taxonomy.json"))
    recovered = False

    def respond(messages: list, schema: type) -> dict:
        text = json.loads(messages[1].content)["UNTRUSTED_RESEARCH_CONTENT"]["text"]
        assert "central contribution" in messages[0].content
        if "low" in text:
            return {"topics": [{"slug": "agent", "confidence": 0.59}]}
        if not recovered and "invalid" in text:
            return {"topics": [{"slug": "not-a-topic", "confidence": 1}]}
        if not recovered and "broken" in text:
            raise TimeoutError("untrusted error text that must not be persisted")
        return {"topics": [{"slug": "agent", "confidence": 0.9}]}

    provider = FakeLLMProvider(respond)
    admission = AdmissionService(factory, provider, topics, 4)
    embedding = FakeEmbeddingProvider()
    embedding.embed = AsyncMock(wraps=embedding.embed)
    ingestion = IngestionService(factory, admission, embedding)
    rows = [
        paper(i, title)
        for i, title in enumerate(
            [
                "Fossil chemistry",
                "Agent low",
                "Agent invalid",
                "Agent broken",
                "Agent good",
                "Agent later",
            ],
            1,
        )
    ]
    # The budget belongs to the whole collection, not separately to each source.
    collectors = [Collector(rows[:5]), Collector(rows[5:], "second")]
    first = await ingestion.collect(collectors, NOW - timedelta(days=7), NOW)
    assert first["fixture"]["count"] == 1
    assert first["fixture"]["prefiltered"] == 1
    assert first["fixture"]["rejected"] == 1
    assert first["fixture"]["failed"] == 2
    assert first["fixture"]["status"] == "partial"
    assert first["second"]["deferred"] == 1
    assert first["second"]["count"] == 0
    assert first["second"]["status"] == "partial"
    assert provider.calls == 4
    assert embedding.embed.await_count == 1
    async with factory() as session:
        for model in (Paper, PaperSourceRecord, PaperTopic, PaperMetric, GenerationRecord):
            assert await session.scalar(select(func.count()).select_from(model)) == 1
        records = list(await session.scalars(select(AdmissionRecord)))
        assert len(records) == 6
        assert {r.status for r in records} == {
            "prefiltered",
            "rejected",
            "failed",
            "accepted",
            "deferred",
        }
        assert {r.error for r in records if r.status == "failed"} == {"ValueError", "TimeoutError"}
        # Audit records contain neither titles, abstracts nor provider exception messages.
        for record in records:
            serialized = json.dumps(
                {c.name: getattr(record, c.name) for c in AdmissionRecord.__table__.columns},
                default=str,
            )
            assert all(raw.title not in serialized for raw in rows)
            assert "Source material" not in serialized and "untrusted error" not in serialized

    recovered = True
    second = await ingestion.collect(collectors, NOW - timedelta(days=7), NOW)
    assert provider.calls == 6  # Schema failure is cached; timeout and deferred can retry.
    assert second["fixture"]["failed"] == 1
    assert second["fixture"]["count"] == 2 and second["second"]["count"] == 1
    admission.retry_failed = True  # Explicit retry after fixing the classifier configuration.
    second = await ingestion.collect(collectors, NOW - timedelta(days=7), NOW)
    assert provider.calls == 7  # Failed/deferred retry; cached rejection uses no budget.
    assert second["fixture"]["count"] == 3 and second["second"]["count"] == 1
    await ingestion.collect(collectors, NOW - timedelta(days=7), NOW)
    assert provider.calls == 7
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Paper)) == 4
        assert await session.scalar(select(func.count()).select_from(PaperSourceRecord)) == 4
        assert await session.scalar(select(func.count()).select_from(GenerationRecord)) == 4


@pytest.mark.integration
async def test_admission_atomic_write_and_sparse_cross_source_duplicate(
    db_engine: AsyncEngine,
) -> None:
    factory = sessions(db_engine)
    provider = FakeLLMProvider(
        lambda m, s: {"topics": [{"slug": "agent", "confidence": 0.9}]},
    )
    admission = AdmissionService(factory, provider, load_taxonomy(Path("config/taxonomy.json")), 1)
    ingestion = IngestionService(factory, admission)
    raw = paper(1, "Agent durable writes").model_copy(update={"metrics": {"hf_upvotes": -1}})
    result = await ingestion.collect([Collector([raw])], NOW - timedelta(days=7), NOW)
    assert result["fixture"]["count"] == 0 and result["fixture"]["status"] == "partial"
    async with factory() as session:
        for model in (Paper, PaperSourceRecord, PaperTopic, PaperMetric, GenerationRecord):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
    # A transient persistence failure must reuse its successful classifier decision.
    raw.metrics = {"hf_upvotes": 3}
    result = await ingestion.collect([Collector([raw])], NOW - timedelta(days=7), NOW)
    assert result["fixture"]["count"] == 1 and provider.calls == 1
    sparse = raw.model_copy(
        update={"source": "huggingface", "title": "Sparse metadata", "abstract": None}
    )
    admission.classification_budget = 0
    result = await ingestion.collect([Collector([sparse])], NOW - timedelta(days=7), NOW)
    assert result["fixture"]["count"] == 1 and provider.calls == 1
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Paper)) == 1
        assert await session.scalar(select(func.count()).select_from(PaperSourceRecord)) == 2
        assert await session.scalar(select(func.count()).select_from(PaperTopic)) == 1
        assert await session.scalar(select(func.count()).select_from(GenerationRecord)) == 1
    # Source mapping cannot bypass conflicting DOI/arXiv identifiers.
    conflict = sparse.model_copy(update={"arxiv_id": "2609.99999"})
    result = await ingestion.collect([Collector([conflict])], NOW - timedelta(days=7), NOW)
    assert result["fixture"]["count"] == 0 and result["fixture"]["status"] == "partial"


@pytest.mark.integration
async def test_admission_rechecks_changed_metadata_and_taxonomy(db_engine: AsyncEngine) -> None:
    factory = sessions(db_engine)
    topics = load_taxonomy(Path("config/taxonomy.json"))
    provider = FakeLLMProvider(
        lambda m, s: {"topics": [{"slug": "agent", "confidence": 0.9}]},
    )
    rows = [paper(1, "Fossil study"), paper(2, "Acoustic study")]
    service = IngestionService(factory, AdmissionService(factory, provider, topics, 2))
    result = await service.collect([Collector(rows)], NOW - timedelta(days=7), NOW)
    assert result["fixture"]["prefiltered"] == 2 and provider.calls == 0
    rows[0].abstract = "Language model agent architecture."
    result = await service.collect([Collector(rows)], NOW - timedelta(days=7), NOW)
    assert result["fixture"]["count"] == 1 and provider.calls == 1
    topics[0] = topics[0].model_copy(update={"keywords": [*topics[0].keywords, "acoustic"]})
    service = IngestionService(factory, AdmissionService(factory, provider, topics, 2))
    result = await service.collect([Collector(rows)], NOW - timedelta(days=7), NOW)
    assert result["fixture"]["count"] == 2 and provider.calls == 2
