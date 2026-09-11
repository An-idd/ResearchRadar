import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collectors.base import PaperCollector
from app.observability import event
from app.providers.base import EmbeddingProvider
from app.providers.embedding import validate_vectors
from app.storage.models import IngestionRun, utcnow
from app.storage.repository import PaperRepository


class IngestionService:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        embedding: EmbeddingProvider | None = None,
        similarity_threshold: float = 0.96,
    ) -> None:
        self.factory = factory
        self.embedding = embedding
        self.similarity_threshold = similarity_threshold

    async def collect(
        self, collectors: list[PaperCollector], since: datetime, until: datetime
    ) -> dict[str, dict[str, str | int]]:
        if since >= until or since.tzinfo is None or until.tzinfo is None:
            raise ValueError("Expected an aware, increasing time window")
        results: dict[str, dict[str, str | int]] = {}
        for collector in collectors:
            run_key = hashlib.sha256(
                f"{collector.source}:{since.isoformat()}:{until.isoformat()}".encode()
            ).hexdigest()
            async with self.factory() as session, session.begin():
                stmt = insert(IngestionRun).values(
                    run_key=run_key,
                    source=collector.source,
                    since=since,
                    until=until,
                    status="running",
                    count=0,
                    error=None,
                )
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["run_key"],
                        set_={"status": "running", "error": None, "updated_at": utcnow()},
                    )
                )
                run_id = await session.scalar(
                    select(IngestionRun.id).where(IngestionRun.run_key == run_key)
                )
                assert run_id
            count, errors = 0, []
            ids: set[UUID] = set()
            try:
                raw_papers = await collector.collect(since, until)
                observed_at = utcnow()
                for raw in raw_papers:
                    try:
                        vector = None
                        if self.embedding:
                            try:
                                vectors = await self.embedding.embed(
                                    [raw.title + "\n" + (raw.abstract or "")]
                                )
                                validate_vectors(vectors, 1)
                                vector = vectors[0]
                            except Exception as exc:
                                errors.append("embedding:" + type(exc).__name__)
                                event(
                                    "embedding_failed", source=raw.source, error=type(exc).__name__
                                )
                        async with self.factory() as session, session.begin():
                            paper = await PaperRepository(session).ingest(
                                raw,
                                observed_at,
                                vector,
                                self.embedding.model if self.embedding else None,
                                self.similarity_threshold,
                            )
                            ids.add(paper.id)
                            count += 1
                    except Exception as exc:
                        errors.append(type(exc).__name__)
                status = "partial" if errors else "succeeded"
            except Exception as exc:
                errors.append(type(exc).__name__)
                status = "failed"
            async with self.factory() as session, session.begin():
                run = await session.get(IngestionRun, run_id)
                assert run
                run.status, run.count, run.error = (
                    status,
                    count,
                    ",".join(sorted(set(errors))) or None,
                )
                run.updated_at = utcnow()
            event(
                "collection_finished",
                job_id=run_id,
                source=collector.source,
                status=status,
                count=count,
                unique_papers=len(ids),
                errors=errors,
            )
            results[collector.source] = {"status": status, "count": count, "job_id": str(run_id)}
        return results
