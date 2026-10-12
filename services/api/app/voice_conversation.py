"""Local browser microphone sessions over bounded PCM WebSockets.

The HTTP endpoint issues a short lived, single use ticket after normal tenant
authorization. Audio is never written to disk by this module.
"""

import asyncio
import importlib
import logging
import secrets
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db_session
from app.kokoro_service import VOICE_LANGUAGES
from app.models import Agent, Membership, User, VoiceSetting
from app.settings import get_settings

router = APIRouter(prefix="/v1")
logger = logging.getLogger("volvox.voice")
ROOT = Path(__file__).resolve().parents[3]
SAMPLE_RATE = 16000
MAX_AUDIO_BYTES = SAMPLE_RATE * 2 * 20
MAX_SESSIONS = 1
SESSION_SECONDS = 300
MAX_TURNS = 20
_tickets: dict[str, "Ticket"] = {}
_sessions = asyncio.Semaphore(MAX_SESSIONS)
_whisper: Any = None
_whisper_lock = threading.Lock()


@dataclass(frozen=True)
class Ticket:
    organization_id: uuid.UUID
    user_id: uuid.UUID
    agent_id: uuid.UUID
    expires_at: float


def allowed_voice_origin(origin: str | None, expected: str) -> bool:
    """WebSocket origins must exactly match the configured dashboard origin."""
    return bool(origin and expected and origin == expected)


def voice_models_available(service: Any) -> bool:
    return bool(service.voices) and any((ROOT / "models" / "whisper").rglob("model.bin")) and all(find_spec(name) is not None for name in ("faster_whisper", "pipecat"))


def _whisper_model() -> Any:
    global _whisper
    with _whisper_lock:
        if _whisper is None:
            WhisperModel = importlib.import_module("faster_whisper").WhisperModel
            cache = ROOT / "models" / "whisper"
            _whisper = WhisperModel("base.en", device="cpu", compute_type="int8", download_root=str(cache), local_files_only=True)
    return _whisper


def _transcribe(audio: bytes) -> tuple[str, float, float]:
    np = importlib.import_module("numpy")

    samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768.0
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples))))
    if peak < 0.003 and rms < 0.0005:
        return "", peak, rms
    # The browser or Silero already delimits each utterance. A second VAD pass
    # can discard a short, quiet manual turn before Whisper sees it.
    segments, _ = _whisper_model().transcribe(samples, language="en", beam_size=5, vad_filter=False)
    return " ".join(segment.text.strip() for segment in segments).strip(), peak, rms


@router.post("/organizations/{organization_id}/voice-session")
def create_voice_session(
    organization_id: uuid.UUID,
    request: Request,
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    from app.routes import require_membership

    require_membership(db, user, organization_id)
    agent = db.scalar(select(Agent).where(Agent.id == agent_id, Agent.organization_id == organization_id, Agent.enabled.is_(True)))
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    settings = get_settings()
    if settings.environment != "development":
        raise HTTPException(status_code=503, detail="Voice transport requires a configured production media service.")
    if not settings.local_dev_auth_bypass:
        raise HTTPException(status_code=503, detail="Local voice transport is not configured.")
    if not voice_models_available(request.app.state.kokoro):
        raise HTTPException(status_code=503, detail="The local speech models are not ready.")
    now = time.monotonic()
    for key, value in list(_tickets.items()):
        if value.expires_at <= now:
            _tickets.pop(key, None)
    if len(_tickets) >= 100:
        raise HTTPException(status_code=429, detail="Too many pending voice sessions.")
    token = secrets.token_urlsafe(32)
    _tickets[token] = Ticket(organization_id, user.id, agent.id, now + 60)
    logger.info("voice_ticket_issued", extra={"organization_id": str(organization_id), "agent_id": str(agent_id), "request_id": request.state.request_id})
    return {"url": "ws://127.0.0.1:8000/v1/voice/ws", "ticket": token, "expires_in": "60"}


@router.websocket("/voice/ws")
async def voice_socket(websocket: WebSocket) -> None:
    settings = get_settings()
    if settings.environment != "development" or not settings.local_dev_auth_bypass:
        logger.warning("voice_socket_disabled")
        await websocket.close(code=1008)
        return
    if websocket.client is None or websocket.client.host not in {"127.0.0.1", "::1", "testclient"}:
        logger.warning("voice_socket_nonlocal_client", extra={"client_host": websocket.client.host if websocket.client else None})
        await websocket.close(code=1008)
        return
    if not allowed_voice_origin(websocket.headers.get("origin"), "http://127.0.0.1:3000"):
        logger.warning("voice_socket_origin_denied", extra={"origin": websocket.headers.get("origin")})
        await websocket.close(code=1008)
        return
    protocols = [part.strip() for part in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    supplied = next((part.removeprefix("ticket.") for part in protocols if part.startswith("ticket.")), "")
    ticket = _tickets.pop(supplied, None)
    if ticket is None or ticket.expires_at <= time.monotonic():
        logger.warning("voice_socket_ticket_denied")
        await websocket.close(code=1008)
        return
    try:
        await asyncio.wait_for(_sessions.acquire(), timeout=0.1)
    except TimeoutError:
        await websocket.close(code=1013)
        return

    # A short database read validates the saved agent and voice preset again at
    # connection time; no ORM objects survive beyond this scope.
    db = websocket.app.state.session_factory()
    try:
        membership = db.scalar(select(Membership).join(User, User.id == Membership.user_id).where(Membership.organization_id == ticket.organization_id, Membership.user_id == ticket.user_id, Membership.active.is_(True), User.active.is_(True)))
        if membership is None:
            await websocket.close(code=1008)
            _sessions.release()
            return
        agent = db.scalar(select(Agent).where(Agent.id == ticket.agent_id, Agent.organization_id == ticket.organization_id, Agent.enabled.is_(True)))
        if agent is None:
            await websocket.close(code=1008)
            _sessions.release()
            return
        preset = db.scalar(select(VoiceSetting).where(VoiceSetting.organization_id == ticket.organization_id, VoiceSetting.agent_id == agent.id))
        voice = preset.voice_id if preset else str(agent.config.get("voice", "af_sarah"))
        language = preset.language if preset else str(agent.config.get("language", "en-us"))
        speed = preset.speed if preset else 1.0
        if voice not in websocket.app.state.kokoro.voices or VOICE_LANGUAGES.get(voice) != language:
            logger.warning("voice_config_invalid", extra={"organization_id": str(ticket.organization_id), "agent_id": str(agent.id)})
            voice, language, speed = "af_sarah", "en-us", 1.0
        instructions = agent.instructions.strip()[:10000]
        response_length = str(agent.config.get("response_length", "concise"))
        if response_length not in {"concise", "balanced", "detailed"}:
            response_length = "concise"
        greeting = str(agent.config.get("greeting", ""))[:500].strip()
    except Exception:
        _sessions.release()
        raise
    finally:
        db.close()

    send_lock = asyncio.Lock()
    serial = 0
    turn_count = 0
    history: list[dict[str, str]] = []
    audio = bytearray()
    task: asyncio.Task[None] | None = None
    analyzer: Any = None
    speaking = False
    mode = "manual"
    started = time.monotonic()
    session_id = str(uuid.uuid4())

    async def send(message: dict[str, object]) -> None:
        async with send_lock:
            await websocket.send_json(message)

    async def run_turn(turn: int, pcm: bytes) -> None:
        nonlocal turn_count
        timestamps: dict[str, float] = {"start": time.monotonic()}
        try:
            await send({"type": "state", "state": "thinking", "turn": turn})
            transcript, peak, rms = await asyncio.wait_for(asyncio.to_thread(_transcribe, pcm), timeout=40)
            if not transcript:
                logger.info("voice_turn_no_speech", extra={"session_id": session_id, "audio_peak": round(peak, 4), "audio_rms": round(rms, 4), "audio_seconds": round(len(pcm) / (SAMPLE_RATE * 2), 2)})
                message = "The selected microphone sent silence. Choose another microphone and try again." if peak < 0.003 and rms < 0.0005 else "No speech was recognized. Speak closer to the selected microphone and try again."
                await send({"type": "error", "message": message, "turn": turn})
                return
            timestamps["transcribed"] = time.monotonic()
            if turn != serial:
                return
            await send({"type": "transcript", "text": transcript, "turn": turn})
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            run_agent = importlib.import_module("services.voice.volvox_voice.agent").run_agent

            length_rule = {"concise": "Reply in one or two sentences.", "balanced": "Reply in two to four sentences.", "detailed": "Give a useful but brief explanation."}[response_length]
            system = "You are a helpful Volvox voice agent. " + length_rule + " Ask for missing facts and do not invent business information. Do not claim to have tools or transfer calls. " + instructions
            answer, _ = await asyncio.wait_for(run_agent(transcript, history=history, system_instruction=system, handle_signals=False), timeout=65)
            if not answer or turn != serial:
                return
            timestamps["answered"] = time.monotonic()
            await send({"type": "response", "text": answer, "turn": turn})
            await send({"type": "state", "state": "speaking", "turn": turn})
            wav, _rate = await asyncio.wait_for(asyncio.to_thread(websocket.app.state.kokoro.synthesize, answer[:5000], voice, language, speed), timeout=45)
            if turn != serial:
                return
            async with send_lock:
                await websocket.send_bytes(wav)
            timestamps["audio"] = time.monotonic()
            history.extend([{"role": "user", "content": transcript}, {"role": "assistant", "content": answer}])
            history[:] = history[-12:]
            turn_count += 1
            logger.info("voice_turn_complete", extra={"organization_id": str(ticket.organization_id), "session_id": session_id, "transcription_ms": round((timestamps["transcribed"] - timestamps["start"]) * 1000), "llm_ms": round((timestamps["answered"] - timestamps["transcribed"]) * 1000), "tts_ms": round((timestamps["audio"] - timestamps["answered"]) * 1000)})
            await send({"type": "state", "state": "listening", "turn": turn})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("voice_turn_failed", extra={"organization_id": str(ticket.organization_id)})
            if turn == serial:
                await send({"type": "error", "message": "This turn failed. Check Ollama and the voice model, then try again.", "turn": turn})

    async def finish_turn() -> None:
        nonlocal serial, task
        if len(audio) < SAMPLE_RATE * 2 // 3:
            audio.clear()
            await send({"type": "error", "message": "Speak for at least half a second, then try again."})
            return
        serial += 1
        if task and not task.done():
            task.cancel()
        pcm = bytes(audio)
        audio.clear()
        task = asyncio.create_task(run_turn(serial, pcm))

    try:
        await websocket.accept(subprotocol="volvox" if "volvox" in protocols else None)
        await send({"type": "ready", "sample_rate": SAMPLE_RATE, "max_seconds": SESSION_SECONDS})
        if greeting:
            await send({"type": "response", "text": greeting, "turn": 0})
            wav, _ = await asyncio.wait_for(asyncio.to_thread(websocket.app.state.kokoro.synthesize, greeting, voice, language, speed), timeout=45)
            async with send_lock:
                await websocket.send_bytes(wav)
        while time.monotonic() - started < SESSION_SECONDS and turn_count < MAX_TURNS:
            message = await asyncio.wait_for(websocket.receive(), timeout=SESSION_SECONDS)
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                chunk = message["bytes"]
                if not chunk or len(chunk) > 32768 or len(chunk) % 2:
                    await send({"type": "error", "message": "Invalid microphone audio frame."})
                    continue
                if mode == "auto":
                    if analyzer is None:
                        SileroVADAnalyzer = importlib.import_module("pipecat.audio.vad.silero").SileroVADAnalyzer
                        VADParams = importlib.import_module("pipecat.audio.vad.vad_analyzer").VADParams

                        analyzer = SileroVADAnalyzer(sample_rate=SAMPLE_RATE, params=VADParams(confidence=0.72, start_secs=0.16, stop_secs=0.9, min_volume=0.35))
                        analyzer.set_sample_rate(SAMPLE_RATE)
                    VADState = importlib.import_module("pipecat.audio.vad.vad_analyzer").VADState

                    state = await analyzer.analyze_audio(chunk)
                    if state in {VADState.STARTING, VADState.SPEAKING}:
                        if not speaking and task and not task.done():
                            serial += 1
                            task.cancel()
                            await send({"type": "interrupted", "turn": serial})
                        speaking = True
                    audio.extend(chunk)
                    if speaking and state == VADState.QUIET:
                        speaking = False
                        await finish_turn()
                    elif not speaking and len(audio) > SAMPLE_RATE * 2:
                        del audio[:-SAMPLE_RATE * 2]
                else:
                    audio.extend(chunk)
                if len(audio) > MAX_AUDIO_BYTES:
                    audio.clear()
                    speaking = False
                    await send({"type": "error", "message": "The recording exceeded 20 seconds. Try a shorter turn."})
            elif message.get("text"):
                import json

                try:
                    command = json.loads(message["text"])
                except (ValueError, TypeError):
                    await send({"type": "error", "message": "Invalid session command."})
                    continue
                match command.get("type"):
                    case "mode" if command.get("value") in {"manual", "auto"}:
                        mode = command["value"]
                        audio.clear()
                        speaking = False
                    case "turn_end" if mode == "manual":
                        await finish_turn()
                    case "interrupt":
                        serial += 1
                        if task and not task.done():
                            task.cancel()
                        audio.clear()
                        await send({"type": "interrupted", "turn": serial})
                    case "stop":
                        break
                    case _:
                        await send({"type": "error", "message": "Unknown session command."})
        await websocket.close(code=1000)
    except (WebSocketDisconnect, TimeoutError):
        pass
    except Exception:
        logger.exception("voice_session_failed", extra={"organization_id": str(ticket.organization_id)})
        try:
            await send({"type": "error", "message": "The voice session ended unexpectedly."})
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if analyzer is not None:
            await analyzer.cleanup()
        _sessions.release()
        logger.info("voice_session_closed", extra={"organization_id": str(ticket.organization_id), "session_id": session_id})
