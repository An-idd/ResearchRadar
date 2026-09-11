import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.domain import (
    Classification,
    PaperComparison,
    PaperSummary,
    Screening,
    SourceText,
    TextChunk,
    TopicDefinition,
)
from app.intelligence.evidence import validate_evidence
from app.intelligence.prompts import fingerprint, messages
from app.observability import event
from app.papers.parser import fetch_pdf, parse_pdf
from app.providers.base import EmbeddingProvider, LLMProvider
from app.providers.embedding import validate_vectors
from app.storage.intelligence import IntelligenceRepository
from app.storage.models import Paper
from app.topics import shortlist


def metadata_text(paper: Paper) -> str:
    return paper.title + "\n" + (paper.abstract or "")


def abstract_source(paper: Paper, max_chars: int = 12000) -> SourceText:
    text = metadata_text(paper)[:max_chars]
    return SourceText(
        paper_id=paper.id,
        title=paper.title,
        published_at=paper.published_at,
        scope="abstract-only",
        chunks=[
            TextChunk(
                id="abstract",
                section="title-and-abstract",
                page=None,
                start=0,
                end=len(text),
                text=text,
            )
        ],
    )


def limit_source(source: SourceText, max_chars: int) -> SourceText:
    chunks = []
    for chunk in source.chunks:
        if max_chars <= 0:
            break
        text = chunk.text[:max_chars]
        chunks.append(chunk.model_copy(update={"text": text, "end": chunk.start + len(text)}))
        max_chars -= len(text)
    return source.model_copy(update={"chunks": chunks})


class IntelligenceService:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        provider: LLMProvider,
        embedding: EmbeddingProvider,
        client: httpx.AsyncClient,
        settings: Settings,
        topics: list[TopicDefinition],
    ) -> None:
        self.factory, self.provider, self.embedding = factory, provider, embedding
        self.client, self.settings, self.topics = client, settings, topics

    async def generate[T: BaseModel](
        self,
        paper_id: UUID,
        version: str,
        payload: Any,
        schema: type[T],
        sources: list[SourceText],
        validate: Callable[[T], None] | None = None,
    ) -> tuple[T, str]:
        input_hash = fingerprint(payload)
        key = fingerprint([paper_id, version, input_hash, self.provider.name, self.provider.model])
        async with self.factory() as session:
            cached = await IntelligenceRepository(session).generation(key)
            if cached:
                output = schema.model_validate(cached.payload)
                if validate:
                    validate(output)
                return output, key
        result = await self.provider.generate_structured(messages(version, payload), schema)
        if validate:
            validate(result.output)
        values = {
            "paper_id": paper_id,
            "generation_key": key,
            "input_hash": input_hash,
            "task": version.split(":")[0],
            "prompt_version": version,
            "provider": result.provider,
            "model": result.model,
            "payload": result.output.model_dump(mode="json"),
            "source_texts": [s.model_dump(mode="json") for s in sources],
            "usage": result.usage.model_dump(),
        }
        async with self.factory() as session, session.begin():
            repo = IntelligenceRepository(session)
            await repo.save_generation(values)
            if isinstance(result.output, PaperSummary):
                await repo.save_summary(
                    {k: v for k, v in values.items() if k != "task"} | {"scope": sources[0].scope}
                )
        event(
            "llm_generation",
            paper_id=paper_id,
            provider=result.provider,
            model=result.model,
            prompt_version=version,
            input_hash=input_hash,
            **result.usage.model_dump(),
        )
        return result.output, key

    async def classify_and_embed(self, paper: Paper) -> bool:
        source = abstract_source(paper)
        candidates = shortlist(metadata_text(paper), self.topics)
        if not candidates:
            return False

        def valid(result: Classification) -> None:
            slugs = [t.slug for t in result.topics]
            if len(set(slugs)) != len(slugs) or set(slugs) - {t.slug for t in candidates}:
                raise ValueError("unknown or duplicate topic slug")

        result, _ = await self.generate(
            paper.id,
            "topic_classifier:v1",
            {"text": source.chunks[0].text, "candidates": [t.model_dump() for t in candidates]},
            Classification,
            [source],
            valid,
        )
        result.topics = [t for t in result.topics if t.confidence >= 0.6]
        async with self.factory() as session, session.begin():
            await IntelligenceRepository(session).set_topics(paper.id, result)
        if not result.topics:
            return False
        input_hash = fingerprint(metadata_text(paper))
        if (
            paper.embedding_model != self.embedding.model
            or paper.embedding_input_hash != input_hash
        ):
            try:
                vectors = await self.embedding.embed([metadata_text(paper)])
                validate_vectors(vectors, 1)
            except Exception as exc:
                event("embedding_failed", paper_id=paper.id, error=type(exc).__name__)
                return (
                    True  # Preserve classification; analysis can use non-vector prior candidates.
                )
            async with self.factory() as session, session.begin():
                saved = await session.get(Paper, paper.id)
                assert saved
                saved.embedding, saved.embedding_model = vectors[0], self.embedding.model
                saved.embedding_input_hash = input_hash
        return True

    async def source(self, paper: Paper) -> SourceText:
        fallback = abstract_source(paper, min(4000, self.settings.max_input_chars // 2))
        if not self.settings.fulltext_enabled or not paper.pdf_url:
            return fallback
        async with self.factory() as session:
            document = await IntelligenceRepository(session).document(paper)
        if document is None:
            try:
                data = await fetch_pdf(self.client, paper.pdf_url, self.settings.max_pdf_bytes)
                document = await asyncio.to_thread(parse_pdf, data, paper.pdf_url)
                async with self.factory() as session, session.begin():
                    await IntelligenceRepository(session).save_document(paper.id, document)
            except Exception as exc:
                event("fulltext_fallback", paper_id=paper.id, error=type(exc).__name__)
                return fallback
        # Round-robin sections so a long introduction cannot consume the entire budget.
        groups: dict[str, list[TextChunk]] = {}
        for chunk in document.chunks:
            if chunk.section != "references":
                groups.setdefault(chunk.section, []).append(chunk)
        chunks = list(fallback.chunks)
        remaining = self.settings.max_input_chars - sum(len(c.text) for c in chunks)
        index = 0
        while remaining > 0 and any(index < len(group) for group in groups.values()):
            for group in groups.values():
                if index >= len(group) or remaining <= 0:
                    continue
                chunk = group[index]
                text = chunk.text[:remaining]
                chunks.append(
                    chunk.model_copy(update={"text": text, "end": chunk.start + len(text)})
                )
                remaining -= len(text)
            index += 1
        return fallback.model_copy(update={"scope": "full-text", "chunks": chunks})

    async def analyze(self, paper_id: UUID) -> str:
        async with self.factory() as session:
            paper = await session.get(Paper, paper_id)
            if not paper:
                raise LookupError("paper not found")
        if not await self.classify_and_embed(paper):
            return "skipped"
        async with self.factory() as session:
            refreshed = await session.get(Paper, paper_id)
            assert refreshed
            paper = refreshed
        abstract = abstract_source(paper)
        screen, _ = await self.generate(
            paper.id, "paper_screen:v1", abstract.model_dump(mode="json"), Screening, [abstract]
        )
        if not screen.selected:
            return "skipped"
        current = await self.source(paper)
        await self.generate(
            paper.id,
            "paper_summary:v1",
            current.model_dump(mode="json"),
            PaperSummary,
            [current],
            lambda output: validate_evidence(output, [current]),
        )
        async with self.factory() as session:
            priors = await IntelligenceRepository(session).prior_papers(paper)
        if not priors:
            return "succeeded"
        # Reserve a bounded share for each prior, always source-grounded.
        half_budget = self.settings.max_input_chars // 2
        sources = [
            limit_source(current, half_budget),
            *[abstract_source(p, half_budget // len(priors)) for p in priors],
        ]
        await self.generate(
            paper.id,
            "paper_comparison:v1",
            [source.model_dump(mode="json") for source in sources],
            PaperComparison,
            sources,
            lambda output: validate_evidence(output, sources),
        )
        return "succeeded"

    async def prepare(self, since: datetime, until: datetime) -> int:
        async with self.factory() as session, session.begin():
            await IntelligenceRepository(session).sync_topics(self.topics)
            papers = list(
                await session.scalars(
                    select(Paper)
                    .where(Paper.published_at >= since, Paper.published_at < until)
                    .order_by(Paper.published_at.desc(), Paper.id)
                )
            )
        count = 0
        candidates = [p for p in papers if shortlist(metadata_text(p), self.topics)]
        for paper in candidates[: self.settings.classification_budget]:
            try:
                if await self.classify_and_embed(paper):
                    count += 1
            except Exception as exc:
                event("classification_failed", paper_id=paper.id, error=type(exc).__name__)
        return count
