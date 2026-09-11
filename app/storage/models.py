"""SQLAlchemy persistence models; schema changes use Alembic only."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Paper(Base):
    __tablename__ = "papers"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    canonical_id: Mapped[str] = mapped_column(unique=True)
    doi: Mapped[str | None] = mapped_column(unique=True)
    arxiv_id: Mapped[str | None] = mapped_column(unique=True)
    title: Mapped[str]
    normalized_title: Mapped[str] = mapped_column(index=True)
    abstract: Mapped[str | None]
    authors: Mapped[list[str]] = mapped_column(JSONB)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paper_url: Mapped[str]
    pdf_url: Mapped[str | None]
    venue: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    embedding_model: Mapped[str | None]
    embedding_input_hash: Mapped[str | None]


class PaperSourceRecord(Base):
    __tablename__ = "paper_sources"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id"), index=True)
    source: Mapped[str]
    source_id: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Topic(Base):
    __tablename__ = "topics"
    slug: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str]
    parent: Mapped[str | None]


class PaperTopic(Base):
    __tablename__ = "paper_topics"
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    topic_slug: Mapped[str] = mapped_column(ForeignKey("topics.slug"), primary_key=True)
    confidence: Mapped[float] = mapped_column(Float)


class PaperMetric(Base):
    __tablename__ = "paper_metrics"
    __table_args__ = (UniqueConstraint("paper_id", "source", "name", "observed_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id"), index=True)
    source: Mapped[str]
    name: Mapped[str]
    value: Mapped[float | None]
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaperSummaryRecord(Base):
    __tablename__ = "paper_summaries"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id"), index=True)
    generation_key: Mapped[str] = mapped_column(unique=True)
    input_hash: Mapped[str]
    provider: Mapped[str]
    model: Mapped[str]
    prompt_version: Mapped[str]
    scope: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_texts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_key: Mapped[str] = mapped_column(unique=True)
    source: Mapped[str]
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="running")
    count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GenerationRecord(Base):
    __tablename__ = "generations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id"), index=True)
    generation_key: Mapped[str] = mapped_column(unique=True)
    input_hash: Mapped[str]
    task: Mapped[str] = mapped_column(index=True)
    provider: Mapped[str]
    model: Mapped[str]
    prompt_version: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_texts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FullTextRecord(Base):
    __tablename__ = "full_text_documents"
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    source_url: Mapped[str]
    content_hash: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    paper_id: Mapped[UUID] = mapped_column(ForeignKey("papers.id"), unique=True)
    status: Mapped[str] = mapped_column(default="queued", index=True)
    error: Mapped[str | None]
    attempts: Mapped[int] = mapped_column(default=0)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
