"""Validated domain data. No database, HTTP or model SDK dependencies."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RawPaper(Model):
    source: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_at: AwareDatetime
    updated_at: AwareDatetime | None = None
    paper_url: HttpUrl
    pdf_url: HttpUrl | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    venue: str | None = None
    metrics: dict[str, float | None] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TopicDefinition(Model):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str
    description: str
    keywords: list[str]
    parent: str | None = None


class TopicMatch(Model):
    slug: str
    confidence: float = Field(ge=0, le=1)


class Classification(Model):
    topics: list[TopicMatch]


class Screening(Model):
    selected: bool
    reason: str


class Evidence(Model):
    field: str
    paper_id: UUID
    chunk_id: str
    quote: str = Field(min_length=1)


class PaperSummary(Model):
    one_sentence: str
    problem: str | None
    why_problem_matters: str | None
    previous_approaches: list[str]
    previous_limitations: list[str]
    method: str | None
    key_innovations: list[str]
    experiment_setup: str | None
    key_results: list[str]
    limitations: list[str]
    why_it_matters: str | None
    engineering_takeaways: list[str]
    what_changed: str | None
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(min_length=1)


class PaperComparison(Model):
    prior_state: str
    current_change: str
    major_difference: str
    inherited_ideas: list[str]
    new_ideas: list[str]
    tradeoffs: list[str]
    importance: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(min_length=2)


class TextChunk(Model):
    id: str
    section: str
    page: int | None
    start: int
    end: int
    text: str


class FullTextDocument(Model):
    source_url: str
    content_hash: str
    chunks: list[TextChunk]


class SourceText(Model):
    paper_id: UUID
    title: str
    published_at: datetime
    scope: Literal["abstract-only", "full-text"]
    chunks: list[TextChunk]


class Usage(Model):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
