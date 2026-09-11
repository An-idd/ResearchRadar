"""Typed settings; credentials never appear in logs or API responses."""

import os
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: SecretStr = SecretStr("")
    database_url_unpooled: SecretStr = SecretStr("")
    neon_branch: str = "development"
    llm_provider: Literal["codex", "openai"] = "codex"
    codex_command: str = "codex"
    codex_model: str = ""
    codex_timeout_seconds: float = Field(default=180, gt=0)
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = Field(default=384, gt=0)
    embedding_cache: Path = Path(".cache/embeddings")
    dedup_similarity_threshold: float = Field(default=0.96, ge=0.90, le=1)
    taxonomy_path: Path = Path("config/taxonomy.json")
    ranking_path: Path = Path("config/ranking.json")
    classification_budget: int = Field(default=50, ge=0, le=1000)
    summary_budget: int = Field(default=5, ge=0, le=100)
    fulltext_enabled: bool = True
    max_pdf_bytes: int = Field(default=15_000_000, gt=0)
    max_input_chars: int = Field(default=24_000, ge=1000)
    collector_limit: int = Field(default=200, ge=1, le=2000)
    arxiv_query: str = "cat:cs.AI OR cat:cs.CL OR cat:cs.LG"
    openreview_venue: str = "ICLR.cc/2026/Conference"
    semantic_scholar_api_key: SecretStr = SecretStr("")
    admin_token: SecretStr = SecretStr("")
    poll_seconds: float = Field(default=5, gt=0)
    collect_interval_seconds: float = Field(default=14400, ge=60)


def get_settings() -> Settings:
    return Settings(_env_file=os.getenv("RADAR_ENV_FILE", ".env.development"))
