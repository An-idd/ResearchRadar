import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx

from app.domain import RawPaper
from app.providers.http import request


def content_value(content: dict[str, Any], key: str, default: Any = None) -> Any:
    value = content.get(key, default)
    return value.get("value", default) if isinstance(value, dict) else value


def parse_openreview(body: dict[str, Any]) -> list[RawPaper]:
    papers = []
    for note in body["notes"]:
        content = note["content"]
        if not content_value(content, "title") or note.get("replyto"):
            continue
        ratings = []
        for reply in note.get("details", {}).get("directReplies", []):
            value = content_value(reply.get("content", {}), "rating")
            match = re.match(r"^\s*(\d+(?:\.\d+)?)", str(value)) if value is not None else None
            if match:
                ratings.append(float(match[1]))
        pdf = content_value(content, "pdf")
        papers.append(
            RawPaper.model_validate(
                {
                    "source": "openreview",
                    "source_id": note["id"],
                    "title": content_value(content, "title"),
                    "abstract": content_value(content, "abstract"),
                    "authors": content_value(content, "authors", []),
                    "published_at": datetime.fromtimestamp(
                        (note.get("pdate") or note.get("cdate") or note["tcdate"]) / 1000, UTC
                    ),
                    "paper_url": f"https://openreview.net/forum?id={note['id']}",
                    "pdf_url": urljoin("https://openreview.net", pdf) if pdf else None,
                    "venue": content_value(content, "venueid"),
                    "doi": content_value(content, "doi"),
                    "arxiv_id": content_value(content, "arxiv_id"),
                    "metrics": {
                        "openreview_rating": sum(ratings) / len(ratings) if ratings else None
                    },
                }
            )
        )
    return papers


class OpenReviewCollector:
    source = "openreview"

    def __init__(self, client: httpx.AsyncClient, venue: str, limit: int = 200) -> None:
        self.client, self.venue, self.limit = client, venue, limit

    async def collect(self, since: datetime, until: datetime) -> list[RawPaper]:
        papers: list[RawPaper] = []
        offset = 0
        while offset < self.limit:
            size = min(100, self.limit - offset)
            response = await request(
                self.client,
                "GET",
                "https://api2.openreview.net/notes",
                params={
                    "content.venueid": self.venue,
                    "limit": size,
                    "offset": offset,
                    "sort": "cdate:desc",
                    "details": "directReplies",
                },
            )
            body = response.json()
            batch = parse_openreview(body)
            papers.extend(p for p in batch if since <= p.published_at < until)
            if len(body["notes"]) < size:
                break
            offset += size
        return papers
