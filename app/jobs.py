"""Single-worker durable jobs and bounded ingestion cycles."""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collectors.base import PaperCollector
from app.config import Settings
from app.intelligence.service import IntelligenceService
from app.observability import event
from app.papers.ingestion import IngestionService
from app.providers.enrichment import EnrichmentProvider
from app.service import RadarService
from app.storage.database import make_engine
from app.storage.intelligence import IntelligenceRepository
from app.storage.models import Paper, utcnow
from app.storage.repository import PaperRepository


class Worker:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        intelligence: IntelligenceService,
        radar: RadarService,
        collectors: list[PaperCollector],
        enrichment: EnrichmentProvider,
        settings: Settings,
    ) -> None:
        self.factory, self.intelligence, self.radar = factory, intelligence, radar
        self.collectors, self.enrichment, self.settings = collectors, enrichment, settings

    async def cycle(self, since: datetime, until: datetime) -> None:
        result = await IngestionService(
            self.factory, self.intelligence.embedding, self.settings.dedup_similarity_threshold
        ).collect(self.collectors, since, until)
        prepared = await self.intelligence.prepare(since, until)
        async with self.factory() as session:
            papers = list(
                await session.scalars(
                    select(Paper)
                    .where(Paper.published_at >= since, Paper.published_at < until)
                    .order_by(Paper.published_at.desc())
                    .limit(self.settings.collector_limit)
                )
            )
        for paper in papers:
            try:
                metrics = await self.enrichment.enrich(paper.doi, paper.arxiv_id)
                async with self.factory() as session, session.begin():
                    await PaperRepository(session).save_metrics(
                        paper.id, "semantic_scholar", metrics, utcnow()
                    )
            except Exception as exc:
                event(
                    "enrichment_failed",
                    paper_id=paper.id,
                    source="semantic_scholar",
                    error=type(exc).__name__,
                )
        feed = await self.radar.feed("new", None, since, until, self.settings.summary_budget)
        for item in feed.items:
            if item.topics:
                await self.radar.enqueue(item.paper.id)
        event(
            "cycle_finished",
            sources=result,
            classified=prepared,
            summary_budget=self.settings.summary_budget,
        )

    async def run_job(self) -> bool:
        async with self.factory() as session, session.begin():
            job = await IntelligenceRepository(session).claim_job()
        if job is None:
            return False
        error = None
        try:
            status = await self.intelligence.analyze(job.paper_id)
        except Exception as exc:
            status, error = "failed", type(exc).__name__
        async with self.factory() as session, session.begin():
            await IntelligenceRepository(session).finish_job(job.id, status, error)
        event("analysis_finished", job_id=job.id, paper_id=job.paper_id, status=status, error=error)
        return True

    async def run(self, once: bool = False, collect: bool = True, days: int = 7) -> None:
        # Session advisory locks require the direct endpoint, not transaction pooling.
        lock_engine = make_engine(self.settings.database_url_unpooled.get_secret_value())
        try:
            async with lock_engine.connect() as connection:
                locked = await connection.scalar(text("SELECT pg_try_advisory_lock(7261646173)"))
                await connection.commit()
                if not locked:
                    raise RuntimeError("another ResearchRadar worker is already running")
                try:
                    async with self.factory() as session, session.begin():
                        await IntelligenceRepository(session).recover_jobs()
                    next_collect = 0.0
                    loop = asyncio.get_running_loop()
                    while True:
                        if collect and loop.time() >= next_collect:
                            until = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
                            await self.cycle(until - timedelta(days=days), until)
                            next_collect = loop.time() + self.settings.collect_interval_seconds
                        worked = await self.run_job()
                        if once and not worked:
                            break
                        if not worked:
                            await asyncio.sleep(self.settings.poll_seconds)
                finally:
                    await connection.execute(text("SELECT pg_advisory_unlock(7261646173)"))
                    await connection.commit()
        finally:
            await lock_engine.dispose()
