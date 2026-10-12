import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint

from app.database import check_database, create_database_engine, session_factory
from app.kokoro_service import make_service
from app.logging_config import configure_logging
from app.models import Base, Membership, Organization, User
from app.routes import router
from app.settings import get_settings
from app.voice_conversation import router as voice_router
from app.voice_conversation import voice_models_available

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("volvox.api")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if settings.database_configured:
        engine = app.state.engine_factory(settings)
    else:
        from sqlalchemy import create_engine

        logger.warning("database_url_uses_local_unconfigured_fallback")
        fallback_path = Path(__file__).resolve().parents[3] / ".volvox-local.db"
        engine = create_engine(f"sqlite:///{fallback_path.as_posix()}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
    app.state.db_engine = engine
    app.state.session_factory = session_factory(engine)
    app.state.database_ready = settings.database_configured
    if not settings.database_configured and settings.environment == "development" and settings.local_dev_auth_bypass:
        with app.state.session_factory() as session:
            user = session.scalar(select(User).where(User.auth_subject == "local-development"))
            if user is None:
                user = User(auth_subject="local-development", email="local@volvox.test", active=True)
                org = Organization(name="Local Volvox workspace")
                session.add_all([user, org])
                session.flush()
                session.add(Membership(organization_id=org.id, user_id=user.id, auth_subject=user.auth_subject, role="owner", active=True))
                session.commit()
    if not hasattr(app.state, "kokoro"):
        app.state.kokoro = make_service()
        await __import__("asyncio").to_thread(app.state.kokoro.load)
    logger.info("api_starting", extra={"environment": settings.environment})
    try:
        yield
    finally:
        engine.dispose()
        logger.info("api_stopping")


app = FastAPI(title="Volvox API", version="0.1.0", lifespan=lifespan)
app.state.engine_factory = create_database_engine
app.include_router(router)
app.include_router(voice_router)


@app.middleware("http")
async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
    supplied = request.headers.get("x-request-id", "")
    request_id = supplied if REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_request_error", extra={"request_id": request_id})
        response = JSONResponse(
            {"detail": "Internal server error", "request_id": request_id}, status_code=500
        )
    logger.info(
        "request_complete",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "status_code": response.status_code,
        },
    )
    response.headers["x-request-id"] = request_id
    return response


@app.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"], response_model=None)
async def ready() -> dict[str, str] | Response:
    if not getattr(app.state, "database_ready", True):
        return JSONResponse({"status": "not_ready", "database": "not_configured"}, status_code=503)
    engine = getattr(app.state, "db_engine", None)
    if engine is None:
        return JSONResponse({"status": "not_ready", "database": "not_started"}, status_code=503)
    try:
        check_database(engine)
    except SQLAlchemyError:
        logger.error("readiness_database_check_failed")
        return JSONResponse({"status": "not_ready", "database": "unavailable"}, status_code=503)
    return {"status": "ready", "database": "available"}


@app.get("/health/services", tags=["health"])
async def services() -> dict[str, str]:
    kokoro = getattr(app.state, "kokoro", None)
    voice = "connected" if kokoro is not None and bool(kokoro.voices) else "unavailable"
    voice_transport = "configured" if settings.environment == "development" and settings.local_dev_auth_bypass and kokoro is not None and voice_models_available(kokoro) else "unavailable"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
            models = response.json().get("models", []) if response.is_success else []
            installed = {item.get("name") for item in models if isinstance(item, dict)}
            ollama = "connected" if settings.chat_model in installed else "unavailable"
    except Exception:
        ollama = "unavailable"
    return {
        "api": "connected",
        "database": "connected" if getattr(app.state, "database_ready", False) else "not_configured",
        "ollama": ollama,
        "voice": voice,
        "voice_transport": voice_transport,
    }
