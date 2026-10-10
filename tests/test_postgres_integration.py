"""Run with VOLVOX_TEST_DATABASE_URL pointing at a disposable PostgreSQL database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

API_ROOT = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.database import create_database_engine  # noqa: E402
from app.main import app  # noqa: E402


DATABASE_URL = os.getenv("VOLVOX_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="VOLVOX_TEST_DATABASE_URL is unset"
)


def test_empty_database_migration_and_api_lifecycle():
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    env = os.environ.copy()
    env["VOLVOX_DATABASE_URL"] = DATABASE_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            ).scalars()
        )
    assert {
        "organizations",
        "users",
        "memberships",
        "agents",
        "sessions",
        "events",
        "alembic_version",
    } <= tables

    engines = []

    def make_engine(_settings):
        engine_for_app = create_engine(DATABASE_URL, pool_pre_ping=True)
        engines.append(engine_for_app)
        return engine_for_app

    app.state.engine_factory = make_engine
    try:
        with TestClient(app) as client:
            assert client.get("/health/live").status_code == 200
            ready = client.get("/health/ready")
            assert ready.status_code == 200
            assert ready.json() == {"status": "ready", "database": "available"}
        assert engines[-1].pool.checkedout() == 0
        with TestClient(app) as client:
            assert client.get("/health/ready").status_code == 200
        assert engines[-1].pool.checkedout() == 0
    finally:
        for engine_for_app in engines:
            engine_for_app.dispose()
        engine.dispose()


def test_readiness_is_503_if_postgres_is_unavailable():
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
    finally:
        app.state.engine_factory = create_database_engine
        broken.dispose()
