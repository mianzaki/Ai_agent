import os
import sys
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session as DbSession

API_ROOT = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.auth import Identity, get_current_identity, get_current_user  # noqa: E402
from app.database import create_database_engine, get_db_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Agent, Base, Membership, Organization, User  # noqa: E402


@pytest.fixture
def test_db() -> Generator[DbSession, None, None]:
    configured_url = os.getenv("VOLVOX_TEST_DATABASE_URL")
    db_path = Path.cwd() / f".test-volvox-{uuid.uuid4().hex}.db"
    database_url = configured_url or f"sqlite:///{db_path}"
    kwargs = {}
    if database_url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
    engine = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
    session = DbSession(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def identities(test_db: DbSession):
    users = []
    orgs = []
    agents = []
    for index in (1, 2):
        user = User(
            auth_subject=f"auth-user-{index}",
            email=f"user{index}@example.test",
            active=True,
        )
        organization = Organization(name=f"Organization {index}")
        test_db.add_all([user, organization])
        test_db.flush()
        membership = Membership(
            organization_id=organization.id,
            user_id=user.id,
            auth_subject=user.auth_subject,
            role="owner",
            active=True,
        )
        agent = Agent(
            organization_id=organization.id,
            name=f"Agent {index}",
            instructions="private",
            config={"private": "secret-config"},
        )
        test_db.add_all([membership, agent])
        test_db.flush()
        users.append(user)
        orgs.append(organization)
        agents.append(agent)
    test_db.commit()
    return users, orgs, agents


@pytest.fixture
def api_client(test_db: DbSession, identities):
    users, _orgs, _agents = identities
    app.dependency_overrides[get_db_session] = lambda: test_db
    app.state.engine_factory = lambda _settings: test_db.get_bind()
    app.dependency_overrides[get_current_identity] = lambda: Identity(
        subject=users[0].auth_subject, claims={"sub": users[0].auth_subject}
    )
    app.dependency_overrides[get_current_user] = lambda: users[0]
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    app.state.engine_factory = create_database_engine


@pytest.fixture
def authenticated_client(test_db: DbSession, identities):
    users, _orgs, _agents = identities
    app.dependency_overrides[get_db_session] = lambda: test_db
    app.state.engine_factory = lambda _settings: test_db.get_bind()
    app.dependency_overrides[get_current_identity] = lambda: Identity(
        subject=users[0].auth_subject, claims={"sub": users[0].auth_subject}
    )
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    app.state.engine_factory = create_database_engine
