import re
from pathlib import Path

from pydantic import TypeAdapter

from app.domain import Classification, TopicDefinition
from app.intelligence.prompts import messages
from app.providers.base import Generation, LLMProvider


def load_taxonomy(path: Path) -> list[TopicDefinition]:
    topics = TypeAdapter(list[TopicDefinition]).validate_json(path.read_text(encoding="utf-8"))
    slugs = {t.slug for t in topics}
    if len(slugs) != len(topics) or any(t.parent and t.parent not in slugs for t in topics):
        raise ValueError("duplicate topic or unknown parent")
    return topics


def shortlist(text: str, topics: list[TopicDefinition]) -> list[TopicDefinition]:
    selected = {
        t.slug
        for t in topics
        if any(
            re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", text, flags=re.I) for k in t.keywords
        )
    }
    for topic in topics:
        if topic.slug in selected and topic.parent:
            selected.add(topic.parent)
    return [t for t in topics if t.slug in selected]


async def classify(
    text: str, candidates: list[TopicDefinition], provider: LLMProvider
) -> Generation[Classification]:
    result = await provider.generate_structured(
        messages(
            "topic_classifier:v1",
            {"text": text, "candidates": [t.model_dump() for t in candidates]},
        ),
        Classification,
    )
    allowed = {t.slug for t in candidates}
    slugs = [t.slug for t in result.output.topics]
    if len(set(slugs)) != len(slugs) or any(slug not in allowed for slug in slugs):
        raise ValueError("classifier returned duplicate or unknown topic")
    result.output.topics = [t for t in result.output.topics if t.confidence >= 0.6]
    return result
