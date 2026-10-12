import uuid


def test_authenticated_user_lists_only_member_organizations(
    authenticated_client, identities
):
    _users, orgs, _agents = identities
    response = authenticated_client.get("/v1/organizations")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(orgs[0].id)]


def test_agent_crud_is_scoped_and_hides_cross_tenant_resources(
    authenticated_client, identities
):
    _users, orgs, agents = identities
    own_org, other_org = orgs
    own_agent, other_agent = agents

    assert (
        authenticated_client.get(
            f"/v1/organizations/{own_org.id}/agents/{own_agent.id}"
        ).status_code
        == 200
    )
    assert (
        authenticated_client.get(
            f"/v1/organizations/{own_org.id}/agents/{other_agent.id}"
        ).status_code
        == 404
    )
    assert (
        authenticated_client.get(
            f"/v1/organizations/{other_org.id}/agents/{other_agent.id}"
        ).status_code
        == 404
    )

    created = authenticated_client.post(
        f"/v1/organizations/{own_org.id}/agents",
        json={"name": "New agent", "config": {"voice": "local"}},
    )
    assert created.status_code == 201
    created_id = created.json()["id"]
    assert (
        authenticated_client.patch(
            f"/v1/organizations/{other_org.id}/agents/{created_id}",
            json={"name": "Hijacked"},
        ).status_code
        == 404
    )
    assert (
        authenticated_client.patch(
            f"/v1/organizations/{own_org.id}/agents/{created_id}",
            json={"name": "Updated"},
        ).json()["name"]
        == "Updated"
    )
    assert (
        authenticated_client.delete(
            f"/v1/organizations/{other_org.id}/agents/{created_id}"
        ).status_code
        == 404
    )
    assert (
        authenticated_client.get(
            f"/v1/organizations/{own_org.id}/agents/{created_id}"
        ).status_code
        == 200
    )
    assert (
        authenticated_client.delete(
            f"/v1/organizations/{own_org.id}/agents/{created_id}"
        ).status_code
        == 204
    )
    assert (
        authenticated_client.get(
            f"/v1/organizations/{own_org.id}/agents/{created_id}"
        ).status_code
        == 404
    )


def test_agent_payload_cannot_assign_tenant_or_private_secret_fields(
    authenticated_client, identities
):
    _users, orgs, _agents = identities
    response = authenticated_client.post(
        f"/v1/organizations/{orgs[0].id}/agents",
        json={
            "name": "Safe",
            "organization_id": str(orgs[1].id),
            "api_key": "should-not-log",
        },
    )
    assert response.status_code == 201
    assert response.json()["organization_id"] == str(orgs[0].id)
    assert "api_key" not in response.json()


def test_membership_and_role_are_required_for_writes(
    authenticated_client, identities, test_db
):
    from app.models import Membership

    _users, orgs, _agents = identities
    membership = test_db.query(Membership).filter_by(organization_id=orgs[0].id).one()
    membership.role = "viewer"
    test_db.commit()
    denied = authenticated_client.post(
        f"/v1/organizations/{orgs[0].id}/agents", json={"name": "No write"}
    )
    assert denied.status_code == 403


def test_cross_tenant_access_does_not_leak_sensitive_config(
    authenticated_client, identities
):
    _users, orgs, agents = identities
    denied = authenticated_client.get(
        f"/v1/organizations/{orgs[0].id}/agents/{agents[1].id}"
    )
    assert denied.status_code == 404
    assert "private" not in denied.text


def test_request_id_is_preserved_and_malformed_request_id_replaced(
    authenticated_client, identities
):
    _users, orgs, _agents = identities
    accepted = authenticated_client.get(
        f"/v1/organizations/{orgs[0].id}", headers={"x-request-id": "trace-123"}
    )
    replaced = authenticated_client.get(
        f"/v1/organizations/{orgs[0].id}", headers={"x-request-id": "bad\r\nid"}
    )
    assert accepted.headers["x-request-id"] == "trace-123"
    assert replaced.headers["x-request-id"] != "bad\r\nid"
    uuid.UUID(replaced.headers["x-request-id"])


def test_speech_requires_member_and_returns_wav(authenticated_client, identities):
    _users, orgs, _agents = identities
    own, other = orgs
    denied = authenticated_client.post(f"/v1/organizations/{other.id}/speech", json={"text": "Hello"})
    assert denied.status_code == 404
    response = authenticated_client.post(
        f"/v1/organizations/{own.id}/speech",
        json={"text": "Hello", "voice_id": "af_sarah", "language": "en-us", "speed": 1.0},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")


def test_voice_settings_are_tenant_scoped_and_validate_installed_voice(authenticated_client, identities):
    _users, orgs, _agents = identities
    own, other = orgs
    assert authenticated_client.get(f"/v1/organizations/{other.id}/voice-settings").status_code == 404
    bad = authenticated_client.put(
        f"/v1/organizations/{own.id}/voice-settings",
        json={"voice_id": "not-installed", "language": "en-us", "speed": 1.0},
    )
    assert bad.status_code == 422
