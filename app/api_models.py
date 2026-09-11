from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from app.domain import Model, PaperComparison, PaperSummary, SourceText, Usage
from app.ranking import Score


class PaperView(Model):
    id: UUID
    canonical_id: str
    doi: str | None
    arxiv_id: str | None
    title: str
    abstract: str | None
    authors: list[str]
    published_at: datetime
    paper_url: str
    pdf_url: str | None
    venue: str | None


class SummaryPreview(Model):
    one_sentence: str
    what_changed: str | None
    scope: Literal["abstract-only", "full-text"]
    generated_at: datetime


class FeedItem(Model):
    paper: PaperView
    score: float | None
    explanation: Score
    topics: list[str]
    metrics: dict[str, float | None]
    summary: SummaryPreview | None


class Feed(Model):
    items: list[FeedItem]
    total: int
    offset: int
    limit: int
    since: datetime
    until: datetime


class JobView(Model):
    id: UUID
    paper_id: UUID
    status: Literal["queued", "running", "succeeded", "skipped", "failed"]
    error: str | None
    attempts: int
    updated_at: datetime


class MetricView(Model):
    name: str
    source: str
    value: float | None
    observed_at: datetime


class SourceView(Model):
    source: str
    source_id: str
    raw: dict[str, Any]
    observed_at: datetime


class GenerationView(Model):
    provider: str
    model: str
    prompt_version: str
    input_hash: str
    scope: Literal["abstract-only", "full-text"]
    source_texts: list[SourceText]
    usage: Usage
    created_at: datetime
    comparison_sources: list[SourceText]


class PaperDetail(Model):
    paper: PaperView
    topics: list[str]
    metrics: list[MetricView]
    sources: list[SourceView]
    summary: PaperSummary | None
    comparison: PaperComparison | None
    comparison_status: Literal["ready", "not-generated", "insufficient-prior-papers"]
    generation: GenerationView | None
    job: JobView | None


class TopicView(Model):
    slug: str
    name: str
    description: str
    parent: str | None
