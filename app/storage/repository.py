from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import RawPaper
from app.papers.normalize import canonical_id, normalize, normalize_title
from app.storage.models import Paper, PaperMetric, PaperSourceRecord


class PaperRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(
        self,
        value: RawPaper,
        observed_at: datetime,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
        similarity_threshold: float = 0.96,
    ) -> Paper:
        raw = normalize(value)
        title = normalize_title(raw.title)
        if not title:
            raise ValueError("empty normalized title")
        # ponytail: serialize metadata merges; use keyed locks if ingestion throughput requires it.
        await self.session.execute(text("SELECT pg_advisory_xact_lock(7261646172)"))
        candidates = []
        for column, identity in ((Paper.doi, raw.doi), (Paper.arxiv_id, raw.arxiv_id)):
            if identity:
                found = await self.session.scalar(select(Paper).where(column == identity))
                if found:
                    candidates.append(found)
        source = await self.session.scalar(
            select(PaperSourceRecord).where(
                PaperSourceRecord.source == raw.source, PaperSourceRecord.source_id == raw.source_id
            )
        )
        if source:
            mapped = await self.session.get(Paper, source.paper_id)
            if mapped:
                candidates.append(mapped)
        if len({p.id for p in candidates}) > 1:
            raise ValueError("identity conflict: manual reconciliation required")
        paper = candidates[0] if candidates else None
        if paper is not None and identity_conflict(paper, raw):
            raise ValueError("source has conflicting strong identifiers")
        if paper is None:
            same_title = await self.session.scalars(
                select(Paper)
                .where(Paper.normalized_title == title)
                .order_by(Paper.created_at, Paper.id)
            )
            paper = next((p for p in same_title if not identity_conflict(p, raw)), None)
        if paper is None and embedding is not None:
            distance = Paper.embedding.cosine_distance(embedding)
            nearest = await self.session.execute(
                select(Paper, distance)
                .where(
                    Paper.embedding.is_not(None),
                    Paper.embedding_model == embedding_model,
                    distance <= 0.10,
                )
                .order_by(distance, Paper.id)
                .limit(5)
            )
            candidates_with_similarity = [
                (p, 1 - float(d)) for p, d in nearest if not identity_conflict(p, raw)
            ]
            paper = next(
                (
                    p
                    for p, similarity in candidates_with_similarity
                    if similarity >= similarity_threshold
                ),
                None,
            )
            if paper is None and candidates_with_similarity:
                raw.metadata = {
                    **raw.metadata,
                    "potential_duplicates": [
                        {"paper_id": str(p.id), "similarity": similarity}
                        for p, similarity in candidates_with_similarity
                    ],
                }
        if paper is None:
            paper = Paper(
                canonical_id=canonical_id(raw),
                title=raw.title,
                normalized_title=title,
                abstract=raw.abstract,
                authors=raw.authors,
                published_at=raw.published_at,
                updated_at=raw.updated_at,
                paper_url=str(raw.paper_url),
                pdf_url=str(raw.pdf_url) if raw.pdf_url else None,
                doi=raw.doi,
                arxiv_id=raw.arxiv_id,
                venue=raw.venue,
            )
            await self.create_paper(paper)
        else:
            paper.doi = paper.doi or raw.doi
            paper.arxiv_id = paper.arxiv_id or raw.arxiv_id
            paper.abstract = max((paper.abstract or "", raw.abstract or ""), key=len) or None
            paper.authors = list(dict.fromkeys([*paper.authors, *raw.authors]))
            paper.pdf_url = paper.pdf_url or (str(raw.pdf_url) if raw.pdf_url else None)
            paper.venue = paper.venue or raw.venue
            paper.published_at = min(paper.published_at, raw.published_at)
            if raw.updated_at:
                paper.updated_at = max(paper.updated_at or raw.updated_at, raw.updated_at)
        stmt = insert(PaperSourceRecord).values(
            paper_id=paper.id,
            source=raw.source,
            source_id=raw.source_id,
            payload=raw.model_dump(mode="json"),
            observed_at=observed_at,
        )
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=["source", "source_id"],
                set_={"payload": stmt.excluded.payload, "observed_at": observed_at},
            )
        )
        await self.save_metrics(paper.id, raw.source, raw.metrics, observed_at)
        if embedding is not None and paper.embedding is None:
            from app.intelligence.prompts import fingerprint

            paper.embedding, paper.embedding_model = embedding, embedding_model
            paper.embedding_input_hash = fingerprint(raw.title + "\n" + (raw.abstract or ""))
        await self.session.flush()
        return paper

    async def save_metrics(
        self, paper_id: UUID, source: str, metrics: dict[str, float | None], observed_at: datetime
    ) -> None:
        for name, value in metrics.items():
            if value is not None and value < 0:
                raise ValueError("negative metric")
            stmt = insert(PaperMetric).values(
                paper_id=paper_id, source=source, name=name, value=value, observed_at=observed_at
            )
            await self.session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["paper_id", "source", "name", "observed_at"],
                    set_={"value": value},
                )
            )

    async def create_paper(self, paper: Paper) -> Paper:
        self.session.add(paper)
        await self.session.flush()
        return paper

    async def get_paper(self, paper_id: UUID) -> Paper | None:
        return await self.session.get(Paper, paper_id)

    async def update_paper(self, paper_id: UUID, *, abstract: str) -> Paper:
        paper = await self.get_paper(paper_id)
        if paper is None:
            raise LookupError("paper not found")
        paper.abstract = abstract
        await self.session.flush()
        return paper

    async def list_papers(self, since: datetime, until: datetime, limit: int = 100) -> list[Paper]:
        return list(
            await self.session.scalars(
                select(Paper)
                .where(Paper.published_at >= since, Paper.published_at < until)
                .order_by(Paper.published_at.desc(), Paper.id)
                .limit(limit)
            )
        )


def identity_conflict(paper: Paper, raw: RawPaper) -> bool:
    return bool(
        (paper.doi and raw.doi and paper.doi != raw.doi)
        or (paper.arxiv_id and raw.arxiv_id and paper.arxiv_id != raw.arxiv_id)
    )
