import hashlib
import re
import unicodedata

from app.domain import RawPaper


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", title).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi.strip(), flags=re.I).lower()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", value):
        raise ValueError("invalid DOI")
    return value


def normalize_arxiv(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"^https?://(?:export\.)?arxiv\.org/(?:abs|pdf)/", "", value.strip())
    value = re.sub(r"(?:v\d+)?(?:\.pdf)?$", "", value)
    if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})", value):
        raise ValueError("invalid arXiv ID")
    return value


def normalize(raw: RawPaper) -> RawPaper:
    return raw.model_copy(
        update={
            "title": " ".join(raw.title.split()),
            "doi": normalize_doi(raw.doi),
            "arxiv_id": normalize_arxiv(raw.arxiv_id),
            "source_id": normalize_arxiv(raw.source_id) if raw.source == "arxiv" else raw.source_id,
        }
    )


def canonical_id(raw: RawPaper) -> str:
    if raw.doi:
        return f"doi:{raw.doi}"
    if raw.arxiv_id:
        return f"arxiv:{raw.arxiv_id}"
    return "title:" + hashlib.sha256(normalize_title(raw.title).encode()).hexdigest()
