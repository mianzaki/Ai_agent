import logging
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.database import check_database, create_database_engine, session_factory
from app.logging_config import configure_logging
from app.routes import router
from app.settings import get_settings

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("volvox.api")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    engine = app.state.engine_factory(settings)
    app.state.db_engine = engine
    app.state.session_factory = session_factory(engine)
    logger.info("api_starting", extra={"environment": settings.environment})
    try:
        yield
    finally:
        engine.dispose()
        logger.info("api_stopping")


app = FastAPI(title="Volvox API", version="0.1.0", lifespan=lifespan)
app.state.engine_factory = create_database_engine
app.include_router(router)


@app.middleware("http")
async def request_context(request: Request, call_next):
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
    engine = getattr(app.state, "db_engine", None)
    if engine is None:
        return JSONResponse({"status": "not_ready", "database": "not_started"}, status_code=503)
    try:
        check_database(engine)
    except SQLAlchemyError:
        logger.error("readiness_database_check_failed")
        return JSONResponse({"status": "not_ready", "database": "unavailable"}, status_code=503)
    return {"status": "ready", "database": "available"}
