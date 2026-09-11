from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain import Model
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


class FeedItem(Model):
    paper: PaperView
    score: float | None
    explanation: Score
    topics: list[str]
    metrics: dict[str, float | None]
    summary: dict[str, Any] | None


class Feed(Model):
    items: list[FeedItem]
    total: int
    offset: int
    limit: int
    since: datetime
    until: datetime


class PaperDetail(Model):
    paper: PaperView
    topics: list[str]
    metrics: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    summary: dict[str, Any] | None
    comparison: dict[str, Any] | None
    comparison_status: str
    generation: dict[str, Any] | None
    job: dict[str, Any] | None


class JobView(Model):
    id: UUID
    paper_id: UUID
    status: str
    error: str | None
    attempts: int
    updated_at: datetime


class TopicView(Model):
    slug: str
    name: str
    description: str
    parent: str | None
