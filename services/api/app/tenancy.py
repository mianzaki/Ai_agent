"""Tenant scoped data access helpers. Callers receive organization IDs from auth."""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session as DbSession

from app.models import Agent, Event, Session


def scoped_agents(organization_id: uuid.UUID) -> Select[tuple[Agent]]:
    return select(Agent).where(Agent.organization_id == organization_id)


def scoped_sessions(organization_id: uuid.UUID) -> Select[tuple[Session]]:
    return select(Session).where(Session.organization_id == organization_id)


def scoped_events(organization_id: uuid.UUID, session_id: uuid.UUID) -> Select[tuple[Event]]:
    return select(Event).where(
        Event.organization_id == organization_id,
        Event.session_id == session_id,
    )


def get_agent(db: DbSession, organization_id: uuid.UUID, agent_id: uuid.UUID) -> Agent | None:
    return db.scalar(scoped_agents(organization_id).where(Agent.id == agent_id))
