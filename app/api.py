import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import AwareDatetime

from app.api_models import Feed, JobView, PaperDetail, TopicView
from app.service import RadarService


def routes(service: RadarService, admin_token: str) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/feed", response_model=Feed)
    async def feed(
        type: Literal["new", "hot"] = "new",
        topic: str | None = None,
        since: AwareDatetime | None = None,
        until: AwareDatetime | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Feed:
        """Publication window [since, until), default last 7 days; stable score ordering."""
        end = until or datetime.now(UTC)
        start = since or end - timedelta(days=7)
        if start >= end or end - start > timedelta(days=365):
            raise HTTPException(422, "window must be increasing and at most 365 days")
        return await service.feed(type, topic, start, end, limit, offset)

    @router.get("/papers/{paper_id}", response_model=PaperDetail)
    async def detail(paper_id: UUID) -> PaperDetail:
        """Metadata, metrics, original source records and evidence-grounded analysis."""
        return await service.detail(paper_id)

    @router.post("/papers/{paper_id}/summary", status_code=202, response_model=JobView)
    async def summarize(
        paper_id: UUID, authorization: Annotated[str | None, Header()] = None
    ) -> JobView:
        """Queue a durable, idempotent analysis job. Poll GET /jobs/{id}; run a worker."""
        if admin_token and not secrets.compare_digest(authorization or "", f"Bearer {admin_token}"):
            raise HTTPException(401, "valid Bearer token required")
        return await service.enqueue(paper_id)

    @router.get("/jobs/{job_id}", response_model=JobView)
    async def job(job_id: UUID) -> JobView:
        return await service.job(job_id)

    @router.get("/topics", response_model=list[TopicView])
    async def topics() -> list[TopicView]:
        return await service.topics()

    @router.get("/topics/{slug}", response_model=TopicView)
    async def topic_detail(slug: str) -> TopicView:
        return await service.topic(slug)

    @router.get("/topics/{slug}/papers", response_model=Feed)
    async def topic_papers(
        slug: str,
        type: Literal["new", "hot"] = "new",
        since: AwareDatetime | None = None,
        until: AwareDatetime | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Feed:
        return await feed(type, slug, since, until, limit, offset)

    return router
