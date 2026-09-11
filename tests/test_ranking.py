from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.ranking import RankingConfig, rank_score, weighted_score


def test_missing_is_not_zero() -> None:
    assert weighted_score({"a": 1, "b": None}, {"a": 1, "b": 1}).value == 1
    assert weighted_score({"a": 1, "b": 0}, {"a": 1, "b": 1}).value == 0.5
    assert weighted_score({}, {"a": 1}).value is None


def test_new_and_hot_order() -> None:
    config = RankingConfig.model_validate_json(Path("config/ranking.json").read_text())
    now = datetime.now(UTC)
    fresh = rank_score("new", now, now, 1, {}, config).value
    old = rank_score("new", now - timedelta(days=4), now, 1, {}, config).value
    assert fresh is not None and old is not None and fresh > old
    fresh = rank_score("hot", now, now, 1, {"hf_upvotes": 0}, config).value
    popular = rank_score("hot", now - timedelta(days=4), now, 1, {"hf_upvotes": 100}, config).value
    assert popular is not None and fresh is not None and popular > fresh
