"""Explicit test doubles; never selected by runtime configuration."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.domain import Usage
from app.providers.base import Generation, Message


class FakeLLMProvider:
    name = "fake"
    model = "fixture-v1"

    def __init__(
        self, responder: Callable[[list[Message], type[BaseModel]], dict[str, Any]]
    ) -> None:
        self.responder = responder
        self.calls = 0

    async def generate_structured[T: BaseModel](
        self, messages: list[Message], schema: type[T]
    ) -> Generation[T]:
        self.calls += 1
        return Generation(
            output=schema.model_validate(self.responder(messages, schema)),
            provider=self.name,
            model=self.model,
            usage=Usage(),
        )


class FakeEmbeddingProvider:
    model = "fixture-embedding-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 383 for _ in texts]
