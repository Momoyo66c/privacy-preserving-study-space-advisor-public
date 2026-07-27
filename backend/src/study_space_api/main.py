from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adapters.recommendation import RecommendationAdapter
from .api import router
from .config import Settings, get_settings
from .database import Database
from .errors import BodyLimitMiddleware, RequestIdMiddleware, install_exception_handlers
from .recommendation import RuleBasedRecommendationAdapter
from .services.people_count import PeopleCountPreviewCache
from .services.sound import SoundPreviewCache
from .services.thermal import ThermalPreviewCache
from .services.weather import WeatherService

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
    app.state.sound_cache = SoundPreviewCache()
    app.state.people_count_cache = PeopleCountPreviewCache()
    app.state.weather_service = WeatherService()
    app.state.recommendation_adapter = adapter or RuleBasedRecommendationAdapter()
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )
    install_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
