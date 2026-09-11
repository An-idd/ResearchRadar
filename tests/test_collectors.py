from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.collectors.arxiv import ArxivCollector, parse_arxiv
from app.collectors.huggingface import parse_huggingface
from app.collectors.openreview import parse_openreview
from app.providers.enrichment import SemanticScholarEnrichmentProvider
from app.providers.http import request

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>https://arxiv.org/abs/2609.00001v2</id><title>Agent memory</title>
<summary>Learned retrieval.</summary><author><name>Alice</name></author>
<published>2026-09-10T00:00:00Z</published><updated>2026-09-10T12:00:00Z</updated>
<link title="pdf" href="https://arxiv.org/pdf/2609.00001"/></entry></feed>"""


async def test_arxiv_parser_and_window() -> None:
    assert parse_arxiv(ATOM)[0].authors == ["Alice"]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=ATOM))
    ) as client:
        collector = ArxivCollector(client, "cat:cs.AI")
        assert (
            len(
                await collector.collect(
                    datetime(2026, 9, 10, tzinfo=UTC), datetime(2026, 9, 11, tzinfo=UTC)
                )
            )
            == 1
        )
        assert (
            await collector.collect(
                datetime(2026, 9, 9, tzinfo=UTC), datetime(2026, 9, 10, tzinfo=UTC)
            )
            == []
        )
    with pytest.raises(ValueError):
        parse_arxiv(b"<!DOCTYPE feed><feed/>")


@pytest.mark.parametrize("status,retries", [(429, 3), (503, 3), (400, 1), (401, 1), (403, 1)])
async def test_retry_categories(status: int, retries: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.http.asyncio.sleep", AsyncMock())
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await request(client, "GET", "https://example.org")
    assert len(calls) == retries


def test_huggingface_missing_metric_and_openreview_ratings() -> None:
    paper = parse_huggingface(
        [{"paper": {"id": "2609.00001", "title": "RAG", "publishedAt": "2026-09-10T00:00:00Z"}}]
    )[0]
    assert paper.metrics["hf_upvotes"] is None
    paper = parse_openreview(
        {
            "notes": [
                {
                    "id": "review1",
                    "cdate": 1788998400000,
                    "content": {
                        "title": {"value": "Reasoning"},
                        "pdf": {"value": "/pdf?id=review1"},
                    },
                    "details": {"directReplies": [{"content": {"rating": {"value": "8: Accept"}}}]},
                }
            ]
        }
    )[0]
    assert paper.metrics["openreview_rating"] == 8


async def test_enrichment_404_is_missing() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(404))
    ) as client:
        assert await SemanticScholarEnrichmentProvider(client).enrich(None, "2609.00001") == {}
