import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.domain import Classification, PaperComparison, PaperSummary, RawPaper, Screening
from app.intelligence.service import IntelligenceService
from app.jobs import Worker
from app.main import create_app
from app.papers.ingestion import IngestionService
from app.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from app.ranking import RankingConfig
from app.service import RadarService
from app.storage.database import sessions
from app.storage.intelligence import IntelligenceRepository
from app.storage.models import (
    AnalysisJob,
    GenerationRecord,
    Paper,
    PaperSourceRecord,
    PaperSummaryRecord,
)
from app.topics import load_taxonomy

RANKING = RankingConfig.model_validate_json(Path("config/ranking.json").read_text())


class FixtureCollector:
    source = "fixture"

    async def collect(self, since: datetime, until: datetime) -> list[RawPaper]:
        return [
            RawPaper(
                source="arxiv",
                source_id=f"2609.0000{i}",
                arxiv_id=f"2609.0000{i}",
                title=f"Agent memory method {i}",
                abstract=f"We evaluate learned retrieval policy {i}.",
                published_at=until - timedelta(days=3 - i),
                paper_url=f"https://arxiv.org/abs/2609.0000{i}",
            )
            for i in (1, 2)
        ]


class DuplicateCollector:
    source = "huggingface"

    async def collect(self, since: datetime, until: datetime) -> list[RawPaper]:
        papers = await FixtureCollector().collect(since, until)
        return [
            papers[1].model_copy(update={"source": "huggingface", "metrics": {"hf_upvotes": 42}})
        ]


class BrokenCollector:
    source = "broken"

    async def collect(self, since: datetime, until: datetime) -> list[RawPaper]:
        raise httpx.ReadTimeout("fixture source unavailable")


class FakeEnrichment:
    async def enrich(self, doi: str | None, arxiv_id: str | None) -> dict[str, float | None]:
        return {"citation_count": None}


def responder(prompt: list, schema: type) -> dict:
    data = json.loads(prompt[1].content)["UNTRUSTED_RESEARCH_CONTENT"]
    if schema is Classification:
        return {"topics": [{"slug": "agent", "confidence": 0.95}]}
    if schema is Screening:
        return {"selected": True, "reason": "fixture contribution"}
    if schema is PaperSummary:
        from test_evidence import summary_payload

        value = summary_payload(data["paper_id"], data["chunks"][0]["text"])
        value["what_changed"] = "Introduces a learned retrieval policy."
        value["evidence"].append({**value["evidence"][0], "field": "what_changed"})
        return value
    if schema is PaperComparison:
        values = {
            "prior_state": "Earlier policy",
            "current_change": "New policy",
            "major_difference": "Different policies",
            "inherited_ideas": [],
            "new_ideas": [],
            "tradeoffs": [],
            "importance": 0.7,
        }
        values["evidence"] = [
            {
                "field": field,
                "paper_id": data[index]["paper_id"],
                "chunk_id": data[index]["chunks"][0]["id"],
                "quote": data[index]["chunks"][0]["text"],
            }
            for field, index in [("prior_state", 1), ("current_change", 0), ("major_difference", 0)]
        ]
        return values
    raise AssertionError(schema)


@pytest.mark.integration
async def test_neon_pipeline_api_idempotency_and_recovery(db_engine: AsyncEngine) -> None:
    factory = sessions(db_engine)
    topics = load_taxonomy(Path("config/taxonomy.json"))
    ranking = RANKING
    settings = Settings(fulltext_enabled=False, summary_budget=2, admin_token="test-token")
    provider = FakeLLMProvider(responder)
    embedding = FakeEmbeddingProvider()
    until = datetime(2026, 9, 11, tzinfo=UTC)
    since = until - timedelta(days=7)
    collectors = [FixtureCollector(), DuplicateCollector(), BrokenCollector()]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(500))
    ) as client:
        intelligence = IntelligenceService(factory, provider, embedding, client, settings, topics)
        radar = RadarService(factory, ranking)
        worker = Worker(factory, intelligence, radar, collectors, FakeEnrichment(), settings)
        result = await IngestionService(factory, embedding).collect(collectors, since, until)
        assert result["broken"]["status"] == "failed"
        assert result["fixture"]["status"] == "succeeded"
        await worker.cycle(since, until)
        while await worker.run_job():
            pass
        first_calls = provider.calls
        await worker.cycle(since, until)
        while await worker.run_job():
            pass
        assert provider.calls == first_calls
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(Paper)) == 2
            assert await session.scalar(select(func.count()).select_from(PaperSourceRecord)) == 3
            assert await session.scalar(select(func.count()).select_from(PaperSummaryRecord)) == 2
            assert await session.scalar(select(func.count()).select_from(GenerationRecord)) == 7
        app = create_app(settings, radar)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api:
            response = await api.get(
                "/api/v1/feed",
                params={"topic": "agent", "since": since.isoformat(), "until": until.isoformat()},
            )
            assert response.status_code == 200
            feed = response.json()
            assert feed["total"] == 2 and feed["items"][0]["summary"]["what_changed"]
            identity = feed["items"][0]["paper"]["id"]
            detail = (await api.get(f"/api/v1/papers/{identity}")).json()
            assert detail["comparison_status"] == "ready"
            assert detail["generation"]["comparison_sources"]
            assert (await api.get(f"/api/v1/papers/{uuid4()}")).status_code == 404
            assert (await api.get("/api/v1/feed?limit=101")).status_code == 422
            assert (await api.post(f"/api/v1/papers/{identity}/summary")).status_code == 401
            headers = {"Authorization": "Bearer test-token"}
            one = await api.post(f"/api/v1/papers/{identity}/summary", headers=headers)
            two = await api.post(f"/api/v1/papers/{identity}/summary", headers=headers)
            assert one.status_code == 202 and one.json()["id"] == two.json()["id"]
        async with factory() as session, session.begin():
            job = await IntelligenceRepository(session).claim_job()
            assert job and job.status == "running"
        async with factory() as session, session.begin():
            await IntelligenceRepository(session).recover_jobs()
        assert await worker.run_job()
        assert provider.calls == first_calls
        async with factory() as session:
            states = list(await session.scalars(select(AnalysisJob.status)))
            assert states == ["succeeded", "succeeded"]
