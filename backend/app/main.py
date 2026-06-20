from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse

from app.auth.jwt import ensure_jwt_secret_configured
from app.config import settings
from app.database import get_db
from app.logging_config import reset_request_id, set_request_id, setup_logging
from app.middleware.market import MarketMiddleware
from app.observability import init_sentry
from app.routers import (
    admin,
    applications,
    auth,
    companies,
    export_api,
    jobs,
    memberships,
    payments,
    profiles,
    public_api,
    reports,
    users,
    verification,
    webhooks_admin,
)
from app.webhooks import router as webhook_router

logger = logging.getLogger(__name__)
MAX_REQUEST_BODY_SIZE = 1_048_576

TAGS_METADATA = [
    {"name": "auth", "description": "Account, JWT, and OAuth endpoints."},
    {"name": "companies", "description": "Company tenant and domain-verification endpoints."},
    {"name": "memberships", "description": "Company membership invite, accept, suspend, and list endpoints."},
    {"name": "applications", "description": "Recruiter application list and pipeline status endpoints."},
    {"name": "jobs", "description": "Market-scoped job listing and management endpoints."},
    {"name": "profiles", "description": "Talent profile endpoints."},
    {"name": "payments", "description": "Featured-job payment intent endpoints."},
    {"name": "reports", "description": "Community moderation report endpoints."},
    {"name": "admin", "description": "Admin moderation and user-management endpoints."},
    {"name": "moderation", "description": "Platform publication-moderation and verification endpoints."},
    {"name": "users", "description": "Current-user account management endpoints."},
    {"name": "public-api", "description": "Public JSON endpoints that replace Restivus."},
    {"name": "export", "description": "Versioned, read-only export of entities in standard schemas."},
    {"name": "webhook-endpoints", "description": "Outbound webhook endpoint registration and management."},
]


class RequestBodyTooLarge(Exception):
    pass


class RequestBodySizeLimitMiddleware:
    def __init__(self, app, max_body_size: int = MAX_REQUEST_BODY_SIZE) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_size:
                    await PlainTextResponse(
                        "Request body too large", status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                    )(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await PlainTextResponse("Request body too large", status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)(
                scope, receive, send
            )


class SecurityHeadersMiddleware:
    def __init__(self, app, environment: str) -> None:
        self.app = app
        self.environment = environment

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                if self.environment != "development":
                    headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _settings_value(*names: str, default: Any = None) -> Any:
    for name in names:
        value = getattr(settings, name, getattr(settings, name.lower(), None))
        if value not in (None, ""):
            return value
        env_value = os.getenv(name)
        if env_value not in (None, ""):
            return env_value
    return default


def _environment() -> str:
    return str(_settings_value("ENVIRONMENT", "environment", default="development")).strip().lower()


def _cors_origins() -> list[str]:
    default_origins = ["*"] if _environment() == "development" else []
    origins = _settings_value("CORS_ORIGINS", "BACKEND_CORS_ORIGINS", default=default_origins)
    if isinstance(origins, str):
        parsed = [item.strip() for item in origins.split(",") if item.strip()]
        return parsed or default_origins
    return list(origins or default_origins)


def _is_development() -> bool:
    return bool(getattr(settings, "debug", False)) or _environment() not in {"production", "prod"}


def _current_request_id(request: Request) -> str | None:
    return getattr(getattr(request, "state", None), "request_id", None)


def _validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    try:
        raw_errors = exc.errors(include_input=False, include_url=False)
    except TypeError:
        raw_errors = exc.errors()

    return [
        {
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg", "Invalid request"),
            "type": error.get("type", "value_error"),
        }
        for error in raw_errors
    ]


async def _run_with_timeout(operation, timeout: float = 2.0) -> None:
    await asyncio.wait_for(asyncio.to_thread(operation), timeout=timeout)


def _database_health_check(bind: Any) -> None:
    from sqlalchemy import text

    if hasattr(bind, "connect"):
        with bind.connect() as connection:
            connection.execute(text("SELECT 1"))
        return
    bind.execute(text("SELECT 1"))


def _redis_health_check(redis_url: str) -> None:
    from redis import Redis

    client = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        client.ping()
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_jwt_secret_configured()
    yield


def create_app() -> FastAPI:
    setup_logging(settings.log_level)
    init_sentry()

    app = FastAPI(
        title=_settings_value("APP_NAME", default="Employed API"),
        version=_settings_value("API_VERSION", default="0.1.0"),
        lifespan=lifespan,
        openapi_tags=TAGS_METADATA,
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        token = set_request_id(request_id)
        try:
            try:
                response = await call_next(request)
            except Exception as exc:  # noqa: BLE001
                handler = request.app.exception_handlers.get(type(exc)) or request.app.exception_handlers.get(Exception)
                if handler is None:
                    raise
                response = await handler(request, exc)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(token)

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = _validation_errors(exc)
        logger.warning(
            "Request validation failed",
            extra={
                "request_id": _current_request_id(request),
                "path": str(request.url.path),
                "method": request.method,
                "errors": errors,
            },
        )
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": errors})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception while processing request",
            extra={
                "request_id": _current_request_id(request),
                "path": str(request.url.path),
                "method": request.method,
            },
        )
        content: dict[str, Any] = {"detail": "Internal server error"}
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=content)

    app.add_middleware(RequestBodySizeLimitMiddleware, max_body_size=MAX_REQUEST_BODY_SIZE)
    app.add_middleware(SecurityHeadersMiddleware, environment=_environment())
    app.add_middleware(MarketMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(companies.router)
    app.include_router(memberships.router)
    app.include_router(applications.router)
    app.include_router(jobs.router)
    app.include_router(profiles.router)
    app.include_router(payments.router)
    app.include_router(reports.router)
    app.include_router(admin.router)
    app.include_router(users.router)
    app.include_router(verification.router)
    app.include_router(public_api.router)
    app.include_router(export_api.router)
    app.include_router(webhooks_admin.router)
    app.include_router(webhook_router, prefix="/webhooks")

    @app.api_route("/health", methods=["GET", "HEAD"], include_in_schema=False)
    async def health(db: Session = Depends(get_db)) -> JSONResponse:
        components: dict[str, str] = {"db": "ok", "redis": "not_configured"}

        try:
            db_bind = db.get_bind()
            await _run_with_timeout(lambda: _database_health_check(db_bind))
        except Exception:
            logger.exception("Database health check failed")
            components["db"] = "error"

        redis_url = getattr(settings, "redis_url", None)
        if redis_url:
            try:
                await _run_with_timeout(lambda: _redis_health_check(redis_url))
                components["redis"] = "ok"
            except Exception:
                logger.exception("Redis health check failed")
                components["redis"] = "error"

        overall_status = "degraded" if any(value == "error" for value in components.values()) else "ok"
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE if overall_status == "degraded" else status.HTTP_200_OK
        return JSONResponse(status_code=response_status, content={"status": overall_status, **components})

    return app


app = create_app()
