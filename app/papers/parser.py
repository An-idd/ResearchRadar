"""Bounded PDF acquisition and page/section-aware text extraction."""

import asyncio
import hashlib
import io
import re
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader

from app.domain import FullTextDocument, TextChunk

HEADINGS = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*[.\s]+)?(abstract|introduction|related work|background|"
    r"method(?:s|ology)?|approach|experiments?|results?|evaluation|limitations?|"
    r"discussion|conclusions?|references)\s*$",
    re.I,
)
PDF_HOSTS = {"arxiv.org", "export.arxiv.org", "openreview.net"}


def validate_pdf_url(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in PDF_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("PDF URL must use an allowed HTTPS research host")


async def fetch_pdf(client: httpx.AsyncClient, url: str, max_bytes: int) -> bytes:
    """Never follow a redirect before validating its target host."""
    # arXiv Atom feeds still emit HTTP PDF links; fetch their HTTPS equivalent.
    if url.startswith("http://arxiv.org/"):
        url = "https://arxiv.org/" + url.removeprefix("http://arxiv.org/")
    validate_pdf_url(url)
    for attempt in range(3):
        try:
            current = url
            for _ in range(4):
                validate_pdf_url(current)
                async with client.stream("GET", current, follow_redirects=False) as response:
                    if response.is_redirect:
                        current = str(response.url.join(response.headers["location"]))
                        continue
                    response.raise_for_status()
                    if int(response.headers.get("content-length", "0")) > max_bytes:
                        raise ValueError("PDF exceeds size limit")
                    data = bytearray()
                    async for block in response.aiter_bytes():
                        data.extend(block)
                        if len(data) > max_bytes:
                            raise ValueError("PDF exceeds size limit")
                    if not bytes(data).lstrip().startswith(b"%PDF-"):
                        raise ValueError("response is not a PDF")
                    return bytes(data)
            raise ValueError("too many PDF redirects")
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                if exc.response.status_code != 429 and exc.response.status_code < 500:
                    raise
            if attempt == 2:
                raise
            import random

            await asyncio.sleep(2**attempt + random.random())
    raise AssertionError("unreachable")


def parse_pdf(data: bytes, source_url: str, max_pages: int = 100) -> FullTextDocument:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted or len(reader.pages) > max_pages:
        raise ValueError("encrypted PDF or page limit exceeded")
    chunks: list[TextChunk] = []
    section = "front-matter"
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        offset, start = 0, 0
        for line in text.splitlines(keepends=True):
            heading = HEADINGS.match(line)
            if heading:
                append_chunks(chunks, text, section, number, start, offset)
                section = heading[1].lower()
                start = offset
            offset += len(line)
        append_chunks(chunks, text, section, number, start, len(text))
    if not chunks:
        raise ValueError("PDF has no extractable text; OCR is not supported")
    return FullTextDocument(
        source_url=source_url, content_hash=hashlib.sha256(data).hexdigest(), chunks=chunks
    )


def append_chunks(
    chunks: list[TextChunk], text: str, section: str, page: int, start: int, end: int
) -> None:
    for position in range(start, end, 2000):
        stop = min(position + 2000, end)
        value = text[position:stop]
        if value.strip():
            chunks.append(
                TextChunk(
                    id=f"page-{page}-{position}",
                    section=section,
                    page=page,
                    start=position,
                    end=stop,
                    text=value,
                )
            )
