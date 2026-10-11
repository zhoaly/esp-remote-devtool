from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.pages import router as pages_router
from app.api.v2 import router as v2_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.storage.database import create_database_engine, create_session_factory

LOGGER = logging.getLogger(__name__)
configure_logging()


def _error(code: str, message: str, details: dict[str, object], status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"error": {"code": code, "message": message, "details": details}}),
    )


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    current_settings = settings or get_settings()
    current_settings.ensure_directories()
    current_engine = engine or create_database_engine(current_settings)

    application = FastAPI(title="ESP Remote Build Server", version="0.2.0")
    application.state.settings = current_settings
    application.state.engine = current_engine
    application.state.session_factory = create_session_factory(current_engine)
    application.mount("/static", StaticFiles(directory=current_settings.static_dir), name="static")
    application.include_router(v2_router)
    application.include_router(pages_router)

    @application.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return _error(exc.code, exc.message, exc.details, exc.status_code)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error("validation_error", "Request validation failed", {"errors": exc.errors()}, 422)

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error("http_error", str(exc.detail), {}, exc.status_code)

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        LOGGER.error(
            "Unhandled API error",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return _error("internal_error", "Internal server error", {}, 500)

    return application


app = create_app()
