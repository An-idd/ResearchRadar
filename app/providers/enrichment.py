from typing import Protocol
from urllib.parse import quote

import httpx

from app.providers.http import request


class EnrichmentProvider(Protocol):
    async def enrich(self, doi: str | None, arxiv_id: str | None) -> dict[str, float | None]: ...


class SemanticScholarEnrichmentProvider:
    def __init__(self, client: httpx.AsyncClient, api_key: str = "") -> None:
        self.client, self.api_key = client, api_key

    async def enrich(self, doi: str | None, arxiv_id: str | None) -> dict[str, float | None]:
        identity = f"DOI:{doi}" if doi else f"ARXIV:{arxiv_id}" if arxiv_id else None
        if identity is None:
            return {}
        try:
            response = await request(
                self.client,
                "GET",
                "https://api.semanticscholar.org/graph/v1/paper/" + quote(identity, safe=""),
                params={"fields": "citationCount,influentialCitationCount"},
                headers={"x-api-key": self.api_key} if self.api_key else {},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {}
            raise
        body = response.json()
        return {
            "citation_count": body.get("citationCount"),
            "influential_citation_count": body.get("influentialCitationCount"),
        }
