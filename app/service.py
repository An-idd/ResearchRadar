from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api_models import (
    Feed,
    FeedItem,
    GenerationView,
    JobView,
    MetricView,
    PaperDetail,
    PaperView,
    SourceView,
    SummaryPreview,
    TopicView,
)
from app.domain import PaperComparison, PaperSummary
from app.ranking import RankingConfig, rank_score
from app.storage.intelligence import IntelligenceRepository
from app.storage.models import AnalysisJob, Paper
from app.storage.queries import QueryRepository


def paper_view(paper: Paper) -> PaperView:
    return PaperView.model_validate(paper, from_attributes=True)


def job_view(job: AnalysisJob) -> JobView:
    return JobView.model_validate(job, from_attributes=True)


class RadarService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], ranking: RankingConfig) -> None:
        self.factory, self.ranking = factory, ranking

    async def feed(
        self,
        kind: Literal["new", "hot"],
        topic: str | None,
        since: datetime,
        until: datetime,
        limit: int,
        offset: int = 0,
    ) -> Feed:
        if since >= until:
            raise ValueError("since must be before until")
        async with self.factory() as session:
            repo = QueryRepository(session)
            if topic and await repo.topic(topic) is None:
                raise LookupError("topic not found")
            papers = await repo.papers(since, until, topic)
            topics, metrics, summaries = await repo.feed_data([p.id for p in papers])
        items = []
        for paper in papers:
            matches = topics.get(paper.id, [])
            relevance = max(
                (t.confidence for t in matches if not topic or t.topic_slug == topic), default=None
            )
            score = rank_score(
                kind, paper.published_at, until, relevance, metrics.get(paper.id, {}), self.ranking
            )
            items.append(
                FeedItem(
                    paper=paper_view(paper),
                    score=score.value,
                    explanation=score,
                    topics=sorted(t.topic_slug for t in matches),
                    metrics=metrics.get(paper.id, {}),
                    summary=SummaryPreview.model_validate(summaries[paper.id])
                    if paper.id in summaries
                    else None,
                )
            )
        items.sort(
            key=lambda item: (
                -(item.score if item.score is not None else -1),
                -item.paper.published_at.timestamp(),
                str(item.paper.id),
            )
        )
        return Feed(
            items=items[offset : offset + limit],
            total=len(items),
            offset=offset,
            limit=limit,
            since=since,
            until=until,
        )

    async def topics(self) -> list[TopicView]:
        async with self.factory() as session:
            return [
                TopicView.model_validate(t, from_attributes=True)
                for t in await QueryRepository(session).topics()
            ]

    async def topic(self, slug: str) -> TopicView:
        async with self.factory() as session:
            topic = await QueryRepository(session).topic(slug)
            if topic is None:
                raise LookupError("topic not found")
            return TopicView.model_validate(topic, from_attributes=True)

    async def detail(self, paper_id: UUID) -> PaperDetail:
        async with self.factory() as session:
            data = await QueryRepository(session).detail(paper_id)
            if data is None:
                raise LookupError("paper not found")
            summary, comparison, job = (
                data[k] for k in ("summary_record", "comparison_record", "job_record")
            )
            status: Literal["ready", "not-generated", "insufficient-prior-papers"] = (
                "ready" if comparison else "not-generated"
            )
            if summary and not comparison:
                priors = await IntelligenceRepository(session).prior_papers(data["paper"])
                status = "not-generated" if priors else "insufficient-prior-papers"
            return PaperDetail(
                paper=paper_view(data["paper"]),
                topics=data["topics"],
                metrics=[
                    MetricView(
                        name=m.name, source=m.source, value=m.value, observed_at=m.observed_at
                    )
                    for m in data["metrics"]
                ],
                sources=[
                    SourceView(
                        source=s.source,
                        source_id=s.source_id,
                        raw=s.payload,
                        observed_at=s.observed_at,
                    )
                    for s in data["sources"]
                ],
                summary=PaperSummary.model_validate(summary.payload) if summary else None,
                comparison=PaperComparison.model_validate(comparison.payload)
                if comparison
                else None,
                comparison_status=status,
                generation=GenerationView.model_validate(
                    {
                        "provider": summary.provider,
                        "model": summary.model,
                        "prompt_version": summary.prompt_version,
                        "input_hash": summary.input_hash,
                        "scope": summary.scope,
                        "source_texts": summary.source_texts,
                        "usage": summary.usage,
                        "created_at": summary.created_at,
                        "comparison_sources": comparison.source_texts if comparison else [],
                    }
                )
                if summary
                else None,
                job=job_view(job) if job else None,
            )

    async def enqueue(self, paper_id: UUID) -> JobView:
        async with self.factory() as session, session.begin():
            job = await IntelligenceRepository(session).enqueue(paper_id)
            await session.flush()
            return job_view(job)

    async def job(self, job_id: UUID) -> JobView:
        async with self.factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if not job:
                raise LookupError("job not found")
            return job_view(job)
