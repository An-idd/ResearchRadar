from datetime import datetime, timedelta
from typing import Any

import httpx

from app.domain import RawPaper
from app.providers.http import request


def parse_huggingface(body: list[dict[str, Any]]) -> list[RawPaper]:
    papers = []
    for item in body:
        paper = item["paper"]
        identity = paper["id"]
        papers.append(
            RawPaper.model_validate(
                {
                    "source": "huggingface",
                    "source_id": identity,
                    "arxiv_id": identity,
                    "title": paper["title"],
                    "abstract": paper.get("summary"),
                    "authors": [a["name"] for a in paper.get("authors", [])],
                    "published_at": paper["publishedAt"],
                    "paper_url": f"https://huggingface.co/papers/{identity}",
                    "pdf_url": f"https://arxiv.org/pdf/{identity}",
                    "metrics": {"hf_upvotes": paper.get("upvotes")},
                }
            )
        )
    return papers


class HuggingFaceCollector:
    source = "huggingface"

    def __init__(self, client: httpx.AsyncClient, limit: int = 200) -> None:
        self.client, self.limit = client, limit

    async def collect(self, since: datetime, until: datetime) -> list[RawPaper]:
        result: dict[str, RawPaper] = {}
        day = (until - timedelta(microseconds=1)).date()
        while day >= since.date() and len(result) < self.limit:
            response = await request(
                self.client,
                "GET",
                "https://huggingface.co/api/daily_papers",
                params={"date": day.isoformat()},
            )
            for paper in parse_huggingface(response.json()):
                if paper.published_at < until:
                    result[paper.source_id] = paper
                if len(result) >= self.limit:
                    break
            day -= timedelta(days=1)
        return list(result.values())
