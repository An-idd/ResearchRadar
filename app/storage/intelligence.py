from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Classification, FullTextDocument, TopicDefinition
from app.storage.models import (
    AnalysisJob,
    FullTextRecord,
    GenerationRecord,
    Paper,
    PaperSummaryRecord,
    PaperTopic,
    Topic,
    utcnow,
)


class IntelligenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def sync_topics(self, topics: list[TopicDefinition]) -> None:
        for topic in topics:
            values = topic.model_dump(exclude={"keywords"})
            stmt = insert(Topic).values(**values)
            await self.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["slug"],
                    set_={key: value for key, value in values.items() if key != "slug"},
                )
            )

    async def set_topics(self, paper_id: UUID, result: Classification) -> None:
        await self.session.execute(delete(PaperTopic).where(PaperTopic.paper_id == paper_id))
        self.session.add_all(
            [
                PaperTopic(paper_id=paper_id, topic_slug=t.slug, confidence=t.confidence)
                for t in result.topics
            ]
        )

    async def generation(self, key: str) -> GenerationRecord | None:
        result = await self.session.scalars(
            select(GenerationRecord).where(GenerationRecord.generation_key == key)
        )
        return result.first()

    async def save_generation(self, values: dict[str, Any]) -> None:
        await self.session.execute(
            insert(GenerationRecord)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["generation_key"])
        )

    async def save_summary(self, values: dict[str, Any]) -> None:
        await self.session.execute(
            insert(PaperSummaryRecord)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["generation_key"])
        )

    async def document(self, paper: Paper) -> FullTextDocument | None:
        record = await self.session.get(FullTextRecord, paper.id)
        if (
            record
            and record.source_url == paper.pdf_url
            and (paper.updated_at is None or record.created_at >= paper.updated_at)
        ):
            return FullTextDocument.model_validate(record.payload)
        return None

    async def save_document(self, paper_id: UUID, document: FullTextDocument) -> None:
        values = {
            "paper_id": paper_id,
            "source_url": document.source_url,
            "content_hash": document.content_hash,
            "payload": document.model_dump(mode="json"),
            "created_at": utcnow(),
        }
        stmt = insert(FullTextRecord).values(**values)
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=["paper_id"],
                set_={key: value for key, value in values.items() if key != "paper_id"},
            )
        )

    async def prior_papers(self, paper: Paper, limit: int = 5) -> list[Paper]:
        topics = select(PaperTopic.topic_slug).where(PaperTopic.paper_id == paper.id)
        same_topic = select(PaperTopic.paper_id).where(PaperTopic.topic_slug.in_(topics))
        query = select(Paper).where(
            Paper.id != paper.id, Paper.published_at < paper.published_at, Paper.id.in_(same_topic)
        )
        if paper.embedding is not None:
            query = query.where(
                Paper.embedding.is_not(None), Paper.embedding_model == paper.embedding_model
            ).order_by(Paper.embedding.cosine_distance(paper.embedding), Paper.id)
        else:
            query = query.order_by(Paper.published_at.desc(), Paper.id)
        return list(await self.session.scalars(query.limit(min(limit, 5))))

    async def enqueue(self, paper_id: UUID) -> AnalysisJob:
        if await self.session.get(Paper, paper_id) is None:
            raise LookupError("paper not found")
        stmt = insert(AnalysisJob).values(paper_id=paper_id, status="queued")
        await self.session.execute(stmt.on_conflict_do_nothing(index_elements=["paper_id"]))
        job = await self.session.scalar(
            select(AnalysisJob).where(AnalysisJob.paper_id == paper_id).with_for_update()
        )
        assert job
        if job.status in {"failed", "succeeded", "skipped"}:
            job.status, job.error, job.requested_at = "queued", None, utcnow()
        return job

    async def claim_job(self) -> AnalysisJob | None:
        job = await self.session.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.status == "queued")
            .order_by(AnalysisJob.requested_at, AnalysisJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job:
            job.status, job.updated_at = "running", utcnow()
            job.attempts += 1
        return job

    async def finish_job(self, job_id: UUID, status: str, error: str | None = None) -> None:
        await self.session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(status=status, error=error, updated_at=utcnow())
        )

    async def recover_jobs(self) -> None:
        await self.session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.status == "running")
            .values(status="queued", error="worker_restarted", updated_at=utcnow())
        )
