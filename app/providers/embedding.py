import asyncio
import math
from pathlib import Path
from typing import Any


def validate_vectors(vectors: list[list[float]], count: int, dimensions: int = 384) -> None:
    if len(vectors) != count:
        raise ValueError("embedding count mismatch")
    for vector in vectors:
        if len(vector) != dimensions or not all(math.isfinite(v) for v in vector):
            raise ValueError("invalid embedding dimensions or values")
        if not any(vector):
            raise ValueError("zero embedding")


class LocalEmbeddingProvider:
    def __init__(self, model: str, cache_dir: Path, dimensions: int = 384) -> None:
        self.model, self.cache_dir, self.dimensions = model, cache_dir, dimensions
        self._encoder: Any = None
        self._lock = asyncio.Lock()

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if self._encoder is None:
            from fastembed import TextEmbedding

            self._encoder = TextEmbedding(
                model_name=self.model, cache_dir=str(self.cache_dir), threads=2
            )
        return [vector.tolist() for vector in self._encoder.embed(texts)]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with self._lock:
            vectors = await asyncio.to_thread(self._embed, texts)
        validate_vectors(vectors, len(texts), self.dimensions)
        return vectors
