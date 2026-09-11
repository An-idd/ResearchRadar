import io
from unittest.mock import AsyncMock

import httpx
import pytest
from pypdf.errors import PdfReadError
from reportlab.pdfgen import canvas

from app.papers.parser import fetch_pdf, parse_pdf, validate_pdf_url


def pdf_fixture(blank: bool = False) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    if not blank:
        text = pdf.beginText(50, 750)
        for line in [
            "Introduction",
            "Agents need reliable persistent memory.",
            "Method",
            "We learn a memory selection policy.",
            "Results",
            "The policy improves recall on the benchmark.",
            "Limitations",
            "Experiments use only one benchmark.",
        ]:
            text.textLine(line)
        pdf.drawText(text)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def test_sections_offsets_and_bad_pdf() -> None:
    document = parse_pdf(pdf_fixture(), "https://arxiv.org/pdf/2609.00001")
    assert {c.section for c in document.chunks} >= {
        "introduction",
        "method",
        "results",
        "limitations",
    }
    assert all(c.page == 1 and c.end - c.start == len(c.text) for c in document.chunks)
    with pytest.raises(ValueError):
        parse_pdf(pdf_fixture(True), "fixture")
    with pytest.raises(PdfReadError):
        parse_pdf(b"invalid", "fixture")


@pytest.mark.parametrize(
    "url",
    [
        "http://arxiv.org/pdf/a",
        "https://localhost/a",
        "https://arxiv.org.evil.test/a",
        "https://user:pass@arxiv.org/a",
        "https://arxiv.org:8080/a",
    ],
)
def test_pdf_host_boundary(url: str) -> None:
    with pytest.raises(ValueError):
        validate_pdf_url(url)


async def test_download_limit_redirect_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=pdf_fixture()))
    ) as client:
        with pytest.raises(ValueError, match="size limit"):
            await fetch_pdf(client, "https://arxiv.org/pdf/a", 10)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"location": "https://127.0.0.1/private"})
        )
    ) as client:
        with pytest.raises(ValueError, match="allowed"):
            await fetch_pdf(client, "https://arxiv.org/pdf/a", 10000)
    sleep = AsyncMock()
    monkeypatch.setattr("app.papers.parser.asyncio.sleep", sleep)
    calls = []

    def timeout(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        raise httpx.ReadTimeout("timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(httpx.ReadTimeout):
            await fetch_pdf(client, "https://arxiv.org/pdf/a", 10000)
    assert len(calls) == 3


async def test_legacy_arxiv_pdf_uses_https() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.scheme == "https" and req.url.host == "arxiv.org"
        return httpx.Response(200, content=pdf_fixture())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await fetch_pdf(client, "http://arxiv.org/pdf/2609.00001", 100000)).startswith(
            b"%PDF"
        )
