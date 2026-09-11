from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import routes
from app.config import Settings, get_settings
from app.ranking import RankingConfig
from app.service import RadarService
from app.storage.database import make_engine, sessions


def create_app(settings: Settings | None = None, service: RadarService | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = None
    if service is None and settings.database_url.get_secret_value():
        engine = make_engine(settings.database_url.get_secret_value())
        service = RadarService(
            sessions(engine),
            RankingConfig.model_validate_json(settings.ranking_path.read_text(encoding="utf-8")),
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if engine:
            await engine.dispose()

    app = FastAPI(title="ResearchRadar", version="0.1.0", lifespan=lifespan)
    if service:
        app.include_router(routes(service, settings.admin_token.get_secret_value()))

    @app.exception_handler(LookupError)
    async def not_found(request: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Process liveness; does not mutate or migrate the database."""
        return {"status": "ok"}

    return app


app = create_app()
