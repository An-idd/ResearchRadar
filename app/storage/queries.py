from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import (
    AnalysisJob,
    GenerationRecord,
    Paper,
    PaperMetric,
    PaperSourceRecord,
    PaperSummaryRecord,
    PaperTopic,
    Topic,
)


class QueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def papers(self, since: datetime, until: datetime, topic: str | None) -> list[Paper]:
        query = select(Paper).where(Paper.published_at >= since, Paper.published_at < until)
        query = query.where(Paper.id.in_(select(PaperTopic.paper_id)))
        if topic:
            query = query.where(
                Paper.id.in_(select(PaperTopic.paper_id).where(PaperTopic.topic_slug == topic))
            )
        return list(await self.session.scalars(query.order_by(Paper.id)))

    async def feed_data(
        self, ids: list[UUID]
    ) -> tuple[
        dict[UUID, list[PaperTopic]],
        dict[UUID, dict[str, float | None]],
        dict[UUID, dict[str, Any]],
    ]:
        topics: dict[UUID, list[PaperTopic]] = {}
        metrics: dict[UUID, dict[str, float | None]] = {}
        summaries: dict[UUID, dict[str, Any]] = {}
        if not ids:
            return topics, metrics, summaries
        for row in await self.session.scalars(
            select(PaperTopic).where(PaperTopic.paper_id.in_(ids))
        ):
            topics.setdefault(row.paper_id, []).append(row)
        rows = await self.session.scalars(
            select(PaperMetric)
            .where(PaperMetric.paper_id.in_(ids))
            .order_by(
                PaperMetric.paper_id,
                PaperMetric.name,
                PaperMetric.observed_at.desc(),
                PaperMetric.id,
            )
            .distinct(PaperMetric.paper_id, PaperMetric.name)
        )
        for metric in rows:
            metrics.setdefault(metric.paper_id, {})[metric.name] = metric.value
        for summary in await self.session.scalars(
            select(PaperSummaryRecord)
            .where(PaperSummaryRecord.paper_id.in_(ids))
            .order_by(PaperSummaryRecord.paper_id, PaperSummaryRecord.created_at.desc())
            .distinct(PaperSummaryRecord.paper_id)
        ):
            summaries[summary.paper_id] = {
                "one_sentence": summary.payload["one_sentence"],
                "what_changed": summary.payload["what_changed"],
                "scope": summary.scope,
                "generated_at": summary.created_at.isoformat(),
            }
        return topics, metrics, summaries

    async def topics(self) -> list[Topic]:
        return list(await self.session.scalars(select(Topic).order_by(Topic.slug)))

    async def topic(self, slug: str) -> Topic | None:
        return await self.session.get(Topic, slug)

    async def detail(self, paper_id: UUID) -> dict[str, Any] | None:
        paper = await self.session.get(Paper, paper_id)
        if paper is None:
            return None
        topics = list(
            await self.session.scalars(
                select(PaperTopic.topic_slug)
                .where(PaperTopic.paper_id == paper_id)
                .order_by(PaperTopic.topic_slug)
            )
        )
        metrics = list(
            await self.session.scalars(
                select(PaperMetric)
                .where(PaperMetric.paper_id == paper_id)
                .order_by(PaperMetric.observed_at.desc())
            )
        )
        sources = list(
            await self.session.scalars(
                select(PaperSourceRecord).where(PaperSourceRecord.paper_id == paper_id)
            )
        )
        summary = await self.session.scalar(
            select(PaperSummaryRecord)
            .where(PaperSummaryRecord.paper_id == paper_id)
            .order_by(PaperSummaryRecord.created_at.desc())
            .limit(1)
        )
        comparison = await self.session.scalar(
            select(GenerationRecord)
            .where(
                GenerationRecord.paper_id == paper_id, GenerationRecord.task == "paper_comparison"
            )
            .order_by(GenerationRecord.created_at.desc())
            .limit(1)
        )
        job = await self.session.scalar(select(AnalysisJob).where(AnalysisJob.paper_id == paper_id))
        return {
            "paper": paper,
            "topics": topics,
            "metrics": metrics,
            "sources": sources,
            "summary_record": summary,
            "comparison_record": comparison,
            "job_record": job,
        }
