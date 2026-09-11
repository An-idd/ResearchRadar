import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

from app.domain import RawPaper
from app.providers.http import request

NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}


def parse_arxiv(body: bytes) -> list[RawPaper]:
    if b"<!DOCTYPE" in body or b"<!ENTITY" in body:
        raise ValueError("XML entities are not accepted")
    root = ET.fromstring(body)
    papers = []
    for entry in root.findall("a:entry", NS):

        def value(name: str, entry: ET.Element = entry) -> str:
            return " ".join((entry.findtext(name, "", NS)).split())

        url = value("a:id")
        if "/api/errors" in url:
            raise ValueError("arXiv returned an API error entry")
        pdf = next(
            (
                link.attrib["href"]
                for link in entry.findall("a:link", NS)
                if link.attrib.get("title") == "pdf"
            ),
            None,
        )
        papers.append(
            RawPaper.model_validate(
                {
                    "source": "arxiv",
                    "source_id": url.split("/abs/")[-1],
                    "arxiv_id": url.split("/abs/")[-1],
                    "title": value("a:title"),
                    "abstract": value("a:summary"),
                    "paper_url": url,
                    "pdf_url": pdf,
                    "authors": [
                        a.findtext("a:name", "", NS) for a in entry.findall("a:author", NS)
                    ],
                    "published_at": value("a:published"),
                    "updated_at": value("a:updated"),
                    "doi": value("x:doi") or None,
                }
            )
        )
    return papers


class ArxivCollector:
    source = "arxiv"

    def __init__(self, client: httpx.AsyncClient, query: str, limit: int = 200) -> None:
        self.client, self.query, self.limit = client, query, limit

    async def collect(self, since: datetime, until: datetime) -> list[RawPaper]:
        result: list[RawPaper] = []
        start = 0
        while start < self.limit:
            size = min(100, self.limit - start)
            query = f"({self.query}) AND submittedDate:[{since:%Y%m%d%H%M} TO {until:%Y%m%d%H%M}]"
            response = await request(
                self.client,
                "GET",
                "https://export.arxiv.org/api/query",
                params={
                    "search_query": query,
                    "start": start,
                    "max_results": size,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
            )
            batch = parse_arxiv(response.content)
            result.extend(p for p in batch if since <= p.published_at < until)
            if len(batch) < size:
                break
            start += size
            if start < self.limit:
                await asyncio.sleep(3)  # arXiv asks clients to space paginated requests.
        return result
