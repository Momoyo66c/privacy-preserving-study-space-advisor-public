from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adapters.recommendation import RecommendationAdapter
from .adapters.recommendation_stub import StubRecommendationAdapter
from .api import router
from .config import Settings, get_settings
from .database import Database
from .errors import BodyLimitMiddleware, RequestIdMiddleware, install_exception_handlers
from .services.thermal import ThermalPreviewCache

logger = logging.getLogger("study_space_api")


def create_app(settings: Settings | None = None, adapter: RecommendationAdapter | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if settings.edge_api_token is None:
            logger.warning("edge write authentication is disabled; bind only to a trusted network")
        yield
        application.state.database.dispose()

    app = FastAPI(title="Privacy-Preserving Study Space API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = Database(settings.database_url)
    app.state.thermal_cache = ThermalPreviewCache()
    app.state.recommendation_adapter = adapter or StubRecommendationAdapter()
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    install_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
