"""Run with python -m app.cli; all commands use explicit configuration."""

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime, timedelta

import httpx
import uvicorn

from app.collectors.arxiv import ArxivCollector
from app.collectors.base import PaperCollector
from app.collectors.huggingface import HuggingFaceCollector
from app.collectors.openreview import OpenReviewCollector
from app.config import get_settings
from app.intelligence.service import IntelligenceService
from app.jobs import Worker
from app.main import create_app
from app.papers.admission import AdmissionService
from app.papers.ingestion import IngestionService
from app.providers.base import LLMProvider
from app.providers.codex import CodexLLMProvider
from app.providers.embedding import LocalEmbeddingProvider
from app.providers.enrichment import SemanticScholarEnrichmentProvider
from app.providers.openai import OpenAIProvider
from app.ranking import RankingConfig
from app.service import RadarService
from app.storage.database import make_engine, sessions
from app.storage.intelligence import IntelligenceRepository
from app.topics import load_taxonomy


async def execute(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url.get_secret_value())
    factory = sessions(engine)
    topics = load_taxonomy(settings.taxonomy_path)
    ranking = RankingConfig.model_validate_json(settings.ranking_path.read_text(encoding="utf-8"))
    try:
        async with httpx.AsyncClient(
            timeout=30, headers={"User-Agent": "ResearchRadar/0.1"}
        ) as client:
            collectors: list[PaperCollector] = [
                ArxivCollector(client, settings.arxiv_query, settings.collector_limit),
                HuggingFaceCollector(client, settings.collector_limit),
                OpenReviewCollector(client, settings.openreview_venue, settings.collector_limit),
            ]
            if args.sources:
                collectors = [c for c in collectors if c.source in args.sources.split(",")]
                if not collectors:
                    raise ValueError("No recognized source selected")
            provider: LLMProvider = (
                CodexLLMProvider(
                    settings.codex_command, settings.codex_model, settings.codex_timeout_seconds
                )
                if settings.llm_provider == "codex"
                else OpenAIProvider(
                    client,
                    settings.llm_base_url,
                    settings.llm_api_key.get_secret_value(),
                    settings.llm_model,
                )
            )
            embedding = LocalEmbeddingProvider(
                settings.embedding_model, settings.embedding_cache, settings.embedding_dimensions
            )
            intelligence = IntelligenceService(
                factory, provider, embedding, client, settings, topics
            )
            radar = RadarService(factory, ranking)
            async with factory() as session, session.begin():
                await IntelligenceRepository(session).sync_topics(topics)
            until = datetime.fromisoformat(args.until) if args.until else datetime.now(UTC)
            since = (
                datetime.fromisoformat(args.since)
                if args.since
                else until - timedelta(days=args.days)
            )
            if args.command == "collect":
                print(
                    json.dumps(
                        await IngestionService(
                            factory,
                            AdmissionService(
                                factory,
                                provider,
                                topics,
                                settings.classification_budget,
                                retry_failed=settings.retry_failed_admissions,
                            ),
                            embedding,
                            settings.dedup_similarity_threshold,
                        ).collect(collectors, since, until)
                    )
                )
            elif args.command == "prepare":
                print(json.dumps({"classified": await intelligence.prepare(since, until)}))
            elif args.command == "feed":
                print(
                    (
                        await radar.feed(args.type, args.topic, since, until, args.limit)
                    ).model_dump_json()
                )
            else:
                worker = Worker(
                    factory,
                    intelligence,
                    radar,
                    collectors,
                    SemanticScholarEnrichmentProvider(
                        client, settings.semantic_scholar_api_key.get_secret_value()
                    ),
                    settings,
                )
                await worker.run(
                    once=args.command == "run-once", collect=not args.jobs_only, days=args.days
                )
    finally:
        await engine.dispose()


def database_loop_factory() -> asyncio.AbstractEventLoop:
    """Uvicorn's Windows default is Proactor; psycopg requires Selector."""
    return asyncio.SelectorEventLoop()


def main() -> None:
    parser = argparse.ArgumentParser(description="ResearchRadar MVP")
    parser.add_argument(
        "command", choices=["serve", "collect", "prepare", "feed", "run-once", "worker"]
    )
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--sources", help="arxiv,huggingface,openreview")
    parser.add_argument("--topic")
    parser.add_argument("--type", choices=["new", "hot"], default="new")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--jobs-only", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.days <= 365 or not 1 <= args.limit <= 100:
        parser.error("days must be 1..365; limit must be 1..100")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if args.command == "serve":
        settings = get_settings()
        if (
            args.host not in {"127.0.0.1", "localhost", "::1"}
            and not settings.admin_token.get_secret_value()
        ):
            parser.error("Set ADMIN_TOKEN before exposing mutation endpoints beyond localhost")
        uvicorn.run(
            create_app(settings),
            host=args.host,
            port=args.port,
            loop="app.cli:database_loop_factory",
        )
    else:
        try:
            asyncio.run(execute(args))
        except KeyboardInterrupt:
            pass
        except Exception as exc:
            logging.error(json.dumps({"event": "command_failed", "error": type(exc).__name__}))
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
