import json
from pathlib import Path

import pytest

from app.providers.fake import FakeLLMProvider
from app.topics import classify, load_taxonomy, shortlist


@pytest.mark.parametrize(
    "paper", json.loads(Path("tests/fixtures/classification.json").read_text())
)
async def test_thirty_classification_fixtures(paper: dict) -> None:
    topics = load_taxonomy(Path("config/taxonomy.json"))
    candidates = shortlist(paper["text"], topics)
    assert paper["expected"] in {t.slug for t in candidates}
    result = await classify(
        paper["text"],
        candidates,
        FakeLLMProvider(lambda m, s: {"topics": [{"slug": paper["expected"], "confidence": 0.9}]}),
    )
    assert result.output.topics[0].slug == paper["expected"]


async def test_unknown_and_low_confidence() -> None:
    topics = load_taxonomy(Path("config/taxonomy.json"))
    with pytest.raises(ValueError, match="unknown"):
        await classify(
            "agent",
            topics,
            FakeLLMProvider(
                lambda m, s: {"topics": [{"slug": "invented-topic", "confidence": 0.9}]}
            ),
        )
    result = await classify(
        "agent",
        topics,
        FakeLLMProvider(lambda m, s: {"topics": [{"slug": "agent", "confidence": 0.59}]}),
    )
    assert result.output.topics == []
