"""Confirm topic relevance before any paper, source, metric or vector is persisted."""

from dataclasses import dataclass, field
from typing import Literal, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain import Classification, RawPaper, TopicDefinition, TopicMatch, Usage
from app.intelligence.prompts import fingerprint
from app.observability import event
from app.providers.base import LLMProvider
from app.storage.admission import AdmissionRepository
from app.storage.intelligence import IntelligenceRepository
from app.storage.models import Paper, PaperTopic
from app.storage.repository import PaperRepository
from app.topics import classify, shortlist

PROMPT_VERSION = "topic_classifier:v2"
type AdmissionStatus = Literal["accepted", "prefiltered", "rejected", "deferred", "failed"]


def retryable_error(error: str | None) -> bool:
    """Only transient failures retry automatically on a later collection."""
    if error in {
        "TimeoutError",
        "TimeoutException",
        "ReadTimeout",
        "ConnectTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "ConnectError",
        "ReadError",
        "WriteError",
        "RemoteProtocolError",
        "HTTP429",
    }:
        return True
    return bool(
        error and error.startswith("HTTP") and error[4:].isdigit() and 500 <= int(error[4:]) < 600
    )


@dataclass
class AdmissionBudget:
    """A fresh budget per collection call, shared across all sources."""

    remaining: int


@dataclass
class AdmissionDecision:
    key: str
    status: AdmissionStatus
    classification: Classification = field(default_factory=lambda: Classification(topics=[]))
    usage: Usage = field(default_factory=Usage)
    existing: bool = False
    error: str | None = None


class AdmissionService:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        provider: LLMProvider,
        topics: list[TopicDefinition],
        classification_budget: int,
        *,
        retry_failed: bool = False,
    ) -> None:
        if classification_budget < 0:
            raise ValueError("classification budget must be nonnegative")
        self.factory, self.provider, self.topics = factory, provider, topics
        self.classification_budget = classification_budget
        self.retry_failed = retry_failed
        self.policy_hash = fingerprint(
            ["paper_admission:v1", [t.model_dump() for t in topics], 0.6, 12000]
        )

    async def review(self, raw: RawPaper, budget: AdmissionBudget) -> AdmissionDecision:
        """Cache decisions for free; retry only deferred or transiently failed candidates."""
        text = raw.title + "\n" + (raw.abstract or "")
        input_hash = fingerprint(text)
        key = fingerprint(
            [
                raw.source,
                raw.source_id,
                input_hash,
                self.policy_hash,
                self.provider.name,
                self.provider.model,
                PROMPT_VERSION,
            ]
        )
        async with self.factory() as session:
            # Preserve cross-source provenance for already admitted identities, even when
            # the incoming source has no abstract/keywords. Strong conflicts still raise.
            existing = await PaperRepository(session).find_existing(raw)
            if existing:
                matches = list(
                    await session.scalars(
                        select(PaperTopic).where(PaperTopic.paper_id == existing.id)
                    )
                )
                allowed = {t.slug for t in self.topics}
                accepted = [
                    TopicMatch(slug=t.topic_slug, confidence=t.confidence)
                    for t in matches
                    if t.topic_slug in allowed and t.confidence >= 0.6
                ]
                if accepted:
                    return AdmissionDecision(
                        key,
                        "accepted",
                        Classification(topics=accepted),
                        existing=True,
                    )
            cached = await AdmissionRepository(session).get(key)
            if cached and (
                cached.status in {"accepted", "prefiltered", "rejected"}
                or (
                    cached.status == "failed"
                    and not self.retry_failed
                    and not retryable_error(cached.error)
                )
            ):
                return AdmissionDecision(
                    key,
                    cast(AdmissionStatus, cached.status),
                    Classification.model_validate(cached.classification),
                    Usage.model_validate(cached.usage),
                    error=cached.error,
                )
        candidates = shortlist(text, self.topics)
        decision = AdmissionDecision(key, "prefiltered")
        if candidates:
            if budget.remaining == 0:
                decision.status = "deferred"
            else:
                budget.remaining -= 1
                try:
                    result = await classify(
                        text[:12000],
                        candidates,
                        self.provider,
                        version=PROMPT_VERSION,
                    )
                    decision.classification, decision.usage = result.output, result.usage
                    decision.status = "accepted" if result.output.topics else "rejected"
                except Exception as exc:
                    decision.status, decision.error = "failed", type(exc).__name__
                    if isinstance(exc, httpx.HTTPStatusError):
                        decision.error = f"HTTP{exc.response.status_code}"
        async with self.factory() as session, session.begin():
            await AdmissionRepository(session).save(
                {
                    "key": key,
                    "source": raw.source,
                    "source_id": raw.source_id,
                    "input_hash": input_hash,
                    "policy_hash": self.policy_hash,
                    "status": decision.status,
                    "classification": decision.classification.model_dump(mode="json"),
                    "provider": self.provider.name,
                    "model": self.provider.model,
                    "prompt_version": PROMPT_VERSION,
                    "usage": decision.usage.model_dump(),
                    "error": decision.error,
                }
            )
        event(
            "paper_admission",
            source=raw.source,
            source_id=raw.source_id,
            status=decision.status,
            error=decision.error,
            input_hash=input_hash,
            provider=self.provider.name,
            model=self.provider.model,
        )
        return decision

    async def attach(
        self,
        session: AsyncSession,
        paper: Paper,
        raw: RawPaper,
        decision: AdmissionDecision,
    ) -> None:
        """Persist confirmed topics and accepted-input provenance in the paper transaction."""
        if decision.status != "accepted" or not decision.classification.topics:
            raise ValueError("Cannot persist a paper without confirmed relevant topics")
        for match in decision.classification.topics:
            saved = await session.get(PaperTopic, (paper.id, match.slug))
            if saved:
                saved.confidence = max(saved.confidence, match.confidence)
            else:
                session.add(
                    PaperTopic(
                        paper_id=paper.id,
                        topic_slug=match.slug,
                        confidence=match.confidence,
                    )
                )
        if decision.existing:
            return
        text = (raw.title + "\n" + (raw.abstract or ""))[:12000]
        payload = {
            "text": text,
            "candidates": [
                t.model_dump()
                for t in shortlist(
                    raw.title + "\n" + (raw.abstract or ""),
                    self.topics,
                )
            ],
        }
        source = {
            "paper_id": str(paper.id),
            "title": raw.title,
            "published_at": raw.published_at.isoformat(),
            "scope": "abstract-only",
            "chunks": [
                {
                    "id": "abstract",
                    "section": "title-and-abstract",
                    "page": None,
                    "start": 0,
                    "end": len(text),
                    "text": text,
                }
            ],
        }
        await IntelligenceRepository(session).save_generation(
            {
                "paper_id": paper.id,
                "generation_key": fingerprint([paper.id, decision.key]),
                "input_hash": fingerprint(payload),
                "task": "topic_classifier",
                "prompt_version": PROMPT_VERSION,
                "provider": self.provider.name,
                "model": self.provider.model,
                "payload": decision.classification.model_dump(),
                "source_texts": [source],
                "usage": decision.usage.model_dump(),
            }
        )
