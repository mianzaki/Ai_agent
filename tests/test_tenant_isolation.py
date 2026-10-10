import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Event, Session  # noqa: E402
from app.tenancy import scoped_events  # noqa: E402


def test_event_cannot_reference_another_tenants_session(test_db, identities):
    _users, orgs, _agents = identities
    org_a, org_b = orgs
    session_a = Session(organization_id=org_a.id, agent_id=uuid.uuid4())
    test_db.add(session_a)
    with pytest.raises(IntegrityError):
        test_db.flush()


def test_event_query_scopes_both_tenant_and_session(test_db, identities):
    _users, orgs, agents = identities
    sessions = [
        Session(organization_id=orgs[index].id, agent_id=agents[index].id)
        for index in range(2)
    ]
    test_db.add_all(sessions)
    test_db.flush()
    test_db.add_all(
        [
            Event(
                organization_id=orgs[index].id,
                session_id=sessions[index].id,
                sequence=1,
                kind="message",
            )
            for index in range(2)
        ]
    )
    test_db.commit()
    assert len(test_db.scalars(scoped_events(orgs[0].id, sessions[0].id)).all()) == 1
    assert test_db.scalars(scoped_events(orgs[0].id, sessions[1].id)).all() == []


def test_membership_subject_must_match_user_identity(test_db, identities):
    _users, orgs, _agents = identities
    from app.models import Membership

    test_db.add(
        Membership(
            organization_id=orgs[0].id,
            user_id=identities[0][0].id,
            auth_subject="forged-subject",
            role="owner",
            active=True,
        )
    )
    with pytest.raises(IntegrityError):
        test_db.flush()
