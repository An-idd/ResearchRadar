import math
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.domain import Model


class RankingConfig(Model):
    new: dict[str, float]
    hot: dict[str, float]
    decay_hours: float = Field(gt=0)
    metric_scales: dict[str, float]

    @model_validator(mode="after")
    def valid_weights(self) -> "RankingConfig":
        if any(v < 0 for weights in (self.new, self.hot) for v in weights.values()):
            raise ValueError("weights must be nonnegative")
        if any(v <= 0 for v in self.metric_scales.values()):
            raise ValueError("metric scales must be positive")
        return self


class Score(Model):
    value: float | None
    signals: dict[str, float | None]
    available_weights: dict[str, float]


def weighted_score(signals: dict[str, float | None], weights: dict[str, float]) -> Score:
    available = {k: w for k, w in weights.items() if signals.get(k) is not None and w > 0}
    total = sum(available.values())
    normalized = {k: w / total for k, w in available.items()} if total else {}
    value = sum((signals[k] or 0.0) * w for k, w in normalized.items()) if total else None
    return Score(value=value, signals=signals, available_weights=normalized)


def rank_score(
    kind: Literal["new", "hot"],
    published_at: datetime,
    now: datetime,
    relevance: float | None,
    metrics: dict[str, float | None],
    config: RankingConfig,
) -> Score:
    age = max(0, (now - published_at).total_seconds() / 3600)
    signals: dict[str, float | None] = {
        "relevance": relevance,
        "freshness": math.exp(-age / config.decay_hours),
        "novelty": None,
        "source_quality": None,
    }
    for name, scale in config.metric_scales.items():
        value = metrics.get(name)
        signals[name] = (
            min(1, math.log1p(max(0, value)) / math.log1p(scale)) if value is not None else None
        )
    return weighted_score(signals, config.new if kind == "new" else config.hot)
