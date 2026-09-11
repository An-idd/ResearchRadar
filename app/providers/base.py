from typing import Protocol

from pydantic import BaseModel

from app.domain import Model, Usage


class Message(Model):
    role: str
    content: str


class Generation[T: BaseModel](Model):
    output: T
    provider: str
    model: str
    usage: Usage


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate_structured[T: BaseModel](
        self, messages: list[Message], schema: type[T]
    ) -> Generation[T]: ...


class EmbeddingProvider(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
