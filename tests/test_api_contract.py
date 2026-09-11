import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api_models import JobView, SummaryPreview
from app.config import Settings
from app.main import create_app


def test_openapi_exposes_analysis_and_job_contracts() -> None:
    api_schema = create_app(
        Settings(_env_file=None, database_url="postgresql://unused:unused@localhost/unused")
    ).openapi()
    assert json.loads(Path("frontend/openapi.json").read_text(encoding="utf-8")) == api_schema
    schema = api_schema["components"]["schemas"]
    assert schema["FeedItem"]["properties"]["summary"]["anyOf"][0]["$ref"].endswith(
        "/SummaryPreview"
    )
    assert schema["PaperDetail"]["properties"]["summary"]["anyOf"][0]["$ref"].endswith(
        "/PaperSummary"
    )
    assert "source_texts" in schema["GenerationView"]["required"]
    assert schema["JobView"]["properties"]["status"]["enum"] == [
        "queued",
        "running",
        "succeeded",
        "skipped",
        "failed",
    ]


def test_preview_accepts_the_compact_feed_payload_and_jobs_reject_unknown_states() -> None:
    preview = SummaryPreview.model_validate(
        {
            "one_sentence": "A contribution",
            "what_changed": None,
            "scope": "abstract-only",
            "generated_at": "2026-09-11T00:00:00Z",
        }
    )
    assert preview.scope == "abstract-only"
    with pytest.raises(ValidationError):
        JobView.model_validate(
            {
                "id": "11111111-1111-4111-8111-111111111111",
                "paper_id": "11111111-1111-4111-8111-111111111111",
                "status": "imaginary",
                "error": None,
                "attempts": 0,
                "updated_at": "2026-09-11T00:00:00Z",
            }
        )
