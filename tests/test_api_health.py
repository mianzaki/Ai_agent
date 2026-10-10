import os

from fastapi.testclient import TestClient

from app.database import create_database_engine  # noqa: E402
from app.main import app  # noqa: E402


def test_health_routes_and_request_id():
    with TestClient(app) as client:
        live = client.get("/health/live", headers={"x-request-id": "health-check-1"})
        ready = client.get("/health/ready")
    assert live.status_code == 200
    assert live.headers["x-request-id"] == "health-check-1"
    assert live.json() == {"status": "alive"}
    if os.getenv("VOLVOX_TEST_DATABASE_URL"):
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready", "database": "available"}
    else:
        assert ready.status_code == 503


def test_health_and_readiness_require_valid_database_lifecycle():
    from sqlalchemy import create_engine

    broken = create_engine(
        "postgresql+psycopg://invalid:invalid@127.0.0.1:1/missing",
        connect_args={"connect_timeout": 1},
    )
    app.state.engine_factory = lambda _settings: broken
    try:
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 503
        assert broken.pool.checkedout() == 0
    finally:
        app.state.engine_factory = create_database_engine
        broken.dispose()
