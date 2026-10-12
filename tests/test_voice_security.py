import pytest
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.settings import get_settings
from app.voice_conversation import allowed_voice_origin
import app.voice_conversation as voice_conversation


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [
        ("http://127.0.0.1:3000", True),
        ("http://localhost:3000", False),
        ("https://evil.example", False),
        ("null", False),
        ("not a URL", False),
        (None, False),
    ],
)
def test_voice_origin_is_exact(origin, allowed):
    assert allowed_voice_origin(origin, "http://127.0.0.1:3000") is allowed


def test_silent_microphone_audio_does_not_load_whisper(monkeypatch):
    monkeypatch.setattr(voice_conversation, "_whisper_model", lambda: pytest.fail("Whisper should not run on silence"))
    assert voice_conversation._transcribe(bytes(32000)) == ("", 0.0, 0.0)


def test_voice_ticket_is_tenant_scoped_and_one_use(api_client, identities, test_db, monkeypatch):
    monkeypatch.setenv("VOLVOX_LOCAL_DEV_AUTH_BYPASS", "true")
    monkeypatch.setattr(voice_conversation, "voice_models_available", lambda _service: True)
    get_settings.cache_clear()
    previous_factory = app.state.session_factory
    app.state.session_factory = sessionmaker(bind=test_db.get_bind(), expire_on_commit=False)
    try:
        _users, orgs, agents = identities
        denied = api_client.post(
            f"/v1/organizations/{orgs[1].id}/voice-session?agent_id={agents[1].id}"
        )
        assert denied.status_code == 404
        issued = api_client.post(
            f"/v1/organizations/{orgs[0].id}/voice-session?agent_id={agents[0].id}"
        )
        assert issued.status_code == 200
        path = issued.json()["url"].replace("ws://127.0.0.1:8000", "")
        protocols = ["volvox", f"ticket.{issued.json()['ticket']}"]
        with pytest.raises(WebSocketDisconnect):
            with api_client.websocket_connect(path, headers={"origin": "https://evil.example"}, subprotocols=protocols):
                pass
        with api_client.websocket_connect(path, headers={"origin": "http://127.0.0.1:3000"}, subprotocols=protocols) as ws:
            assert ws.receive_json()["type"] == "ready"
            ws.send_json({"type": "stop"})
        with pytest.raises(WebSocketDisconnect):
            with api_client.websocket_connect(path, headers={"origin": "http://127.0.0.1:3000"}, subprotocols=protocols):
                pass
    finally:
        app.state.session_factory = previous_factory
        get_settings.cache_clear()
