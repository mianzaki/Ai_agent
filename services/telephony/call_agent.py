"""Volvox telephony demo — Twilio Media Streams <-> local voice agent.

Step 1 of the SaaS voice agent: one inbound call, fully local models
(faster-whisper -> Ollama -> Kokoro), streamed over Twilio's Media Streams
WebSocket protocol.

IMPORTANT — Twilio is BYPASSABLE. This service needs no Twilio account to run.
A local simulator (simulate_call.py) speaks the exact same Media Streams
protocol, so you can place a full end-to-end "call" right now. When you later
add a Twilio number, point its Voice webhook at POST /voice and nothing else
changes. Twilio request-signature validation stays OFF until you set
TWILIO_AUTH_TOKEN and TWILIO_VALIDATE=1.

Run:  .venv312/bin/python -m uvicorn call_agent:app --app-dir services/telephony --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import asyncio
import audioop
import base64
import importlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import requests
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("volvox.telephony")

ROOT = Path(__file__).resolve().parents[2]

# ---- configuration (all overridable by env; none require Twilio) ----
OLLAMA_URL = os.getenv("VOLVOX_OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("VOLVOX_MODEL", "llama3.2:3b")
KEEP_ALIVE = os.getenv("VOLVOX_OLLAMA_KEEP_ALIVE", "30m")
MAX_TOKENS = int(os.getenv("VOLVOX_MAX_TOKENS", "120"))
VOICE = os.getenv("VOLVOX_VOICE", "af_sarah")
VOICE_LANG = os.getenv("VOLVOX_VOICE_LANG", "en-us")
WHISPER_SIZE = os.getenv("VOLVOX_WHISPER", "base.en")
GREETING = os.getenv(
    "VOLVOX_GREETING",
    "Thank you for calling Volvox Solutions. How can I help you today?",
)
SYSTEM_PROMPT = os.getenv(
    "VOLVOX_SYSTEM",
    "You are a friendly phone receptionist for Volvox Solutions. You are speaking out loud, "
    "so reply in at most two short, natural sentences. Never use markdown, lists, or emojis. "
    "Ask one question at a time, stay on topic, and do not invent facts you were not given.",
)
PUBLIC_WS_URL = os.getenv("VOLVOX_PUBLIC_WS_URL", "")  # e.g. wss://abc123.trycloudflare.com/twilio/ws
TWILIO_VALIDATE = os.getenv("TWILIO_VALIDATE", "0") == "1"
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")

# ---- telephony audio constants ----
TW_RATE = 8000          # Twilio Media Streams: 8 kHz mu-law, mono
FRAME_MS = 20
FRAME_BYTES_ULAW = TW_RATE * FRAME_MS // 1000          # 160 bytes mu-law per 20 ms
FRAME_BYTES_PCM = FRAME_BYTES_ULAW * 2                  # 320 bytes PCM16 per 20 ms
SPEECH_RMS = int(os.getenv("VOLVOX_SPEECH_RMS", "420"))  # 16-bit RMS gate for "is this speech"
ENDPOINT_MS = int(os.getenv("VOLVOX_ENDPOINT_MS", "700"))  # trailing silence that ends a turn
MIN_UTTERANCE_MS = 400
MAX_UTTERANCE_MS = 15000
BARGE_IN_MS = 280       # sustained caller speech this long interrupts the agent


# ======================================================================
# Lazy-loaded local models (shared across calls in this process)
# ======================================================================
_whisper: Any = None
_kokoro: Any = None


def whisper_model() -> Any:
    global _whisper
    if _whisper is None:
        WhisperModel = importlib.import_module("faster_whisper").WhisperModel
        cache = ROOT / "models" / "whisper"
        _whisper = WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8", download_root=str(cache))
        logger.info("whisper loaded (%s, cpu int8)", WHISPER_SIZE)
    return _whisper


def kokoro_model() -> Any:
    global _kokoro
    if _kokoro is None:
        Kokoro = importlib.import_module("kokoro_onnx").Kokoro
        model = os.getenv("VOLVOX_KOKORO_MODEL", str(ROOT / "models" / "kokoro-v1.0.onnx"))
        voices = os.getenv("VOLVOX_KOKORO_VOICES", str(ROOT / "models" / "voices-v1.0.bin"))
        _kokoro = Kokoro(model, voices)
        logger.info("kokoro loaded")
    return _kokoro


# ======================================================================
# Pipeline stages (blocking; always called via asyncio.to_thread)
# ======================================================================
def transcribe(pcm8k: bytes) -> str:
    """mu-law-derived PCM16 @8k -> text."""
    pcm16k, _ = audioop.ratecv(pcm8k, 2, 1, TW_RATE, 16000, None)
    samples = np.frombuffer(pcm16k, dtype="<i2").astype(np.float32) / 32768.0
    if samples.size == 0 or float(np.max(np.abs(samples))) < 0.004:
        return ""
    segments, _ = whisper_model().transcribe(samples, language="en", beam_size=1, vad_filter=False)
    return " ".join(seg.text.strip() for seg in segments).strip()


def ask_ollama(user_text: str, history: list[dict[str, str]]) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history[-8:], {"role": "user", "content": user_text}]
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": MODEL, "messages": messages, "stream": False, "keep_alive": KEEP_ALIVE,
              "options": {"num_predict": MAX_TOKENS, "temperature": 0.7}},
        timeout=60,
    )
    response.raise_for_status()
    return (response.json().get("message", {}).get("content") or "").strip()


def synth_ulaw_frames(text: str) -> list[bytes]:
    """text -> Kokoro speech -> 8 kHz mu-law, split into 20 ms Twilio frames."""
    samples, rate = kokoro_model().create(text[:1000], voice=VOICE, speed=1.0, lang=VOICE_LANG)
    audio = np.asarray(samples, dtype=np.float32)
    if audio.size == 0:
        return []
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    pcm8k, _ = audioop.ratecv(pcm, 2, 1, int(rate), TW_RATE, None)
    ulaw = audioop.lin2ulaw(pcm8k, 2)
    return [ulaw[i:i + FRAME_BYTES_ULAW] for i in range(0, len(ulaw), FRAME_BYTES_ULAW)]


# ======================================================================
# FastAPI app
# ======================================================================
app = FastAPI(title="Volvox Telephony Demo")


@app.get("/health")
def health() -> dict[str, object]:
    ok = True
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=3).raise_for_status()
    except Exception:
        ok = False
    return {"status": "ok", "ollama": ok, "model": MODEL, "twilio_validation": TWILIO_VALIDATE}


@app.api_route("/voice", methods=["GET", "POST"])
async def voice_webhook(request: Request) -> Response:
    """Twilio Voice webhook. Returns TwiML that opens a Media Stream to this service."""
    host = PUBLIC_WS_URL or f"wss://{request.url.hostname}/twilio/ws"
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect>"
        f'<Stream url="{host}"/>'
        "</Connect></Response>"
    )
    return Response(content=twiml, media_type="text/xml")


@app.get("/")
def index() -> PlainTextResponse:
    return PlainTextResponse(
        "Volvox telephony demo is running.\n"
        "- Local test (no Twilio):  python services/telephony/simulate_call.py\n"
        "- Twilio later: point the number's Voice webhook at POST /voice\n"
    )


@app.websocket("/twilio/ws")
async def twilio_stream(ws: WebSocket) -> None:
    await ws.accept()
    stream_sid: str | None = None
    history: list[dict[str, str]] = []
    send_lock = asyncio.Lock()
    play_task: asyncio.Task[None] | None = None
    turn_task: asyncio.Task[None] | None = None
    speaking = False

    # listening state
    buf = bytearray()
    seen_speech = False
    silence_ms = 0
    voiced_ms = 0
    barge_ms = 0

    async def send_event(obj: dict[str, Any]) -> None:
        async with send_lock:
            await ws.send_text(json.dumps(obj))

    async def play(frames: list[bytes]) -> None:
        nonlocal speaking
        speaking = True
        try:
            for frame in frames:
                async with send_lock:
                    await ws.send_text(json.dumps({
                        "event": "media", "streamSid": stream_sid,
                        "media": {"payload": base64.b64encode(frame).decode("ascii")},
                    }))
                await asyncio.sleep(FRAME_MS / 1000)
            await send_event({"event": "mark", "streamSid": stream_sid, "mark": {"name": "agent-done"}})
        except asyncio.CancelledError:
            raise
        finally:
            speaking = False

    async def speak(text: str) -> None:
        nonlocal play_task
        if not text:
            return
        logger.info("AGENT: %s", text)
        frames = await asyncio.to_thread(synth_ulaw_frames, text)
        play_task = asyncio.create_task(play(frames))

    async def run_turn(pcm8k: bytes) -> None:
        t0 = time.monotonic()
        text = await asyncio.to_thread(transcribe, pcm8k)
        if not text:
            logger.info("(no speech recognized in turn)")
            return
        logger.info("CALLER: %s", text)
        answer = await asyncio.to_thread(ask_ollama, text, history)
        if not answer:
            return
        history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": answer}])
        del history[:-16]
        await speak(answer)
        logger.info("turn latency: %.1fs", time.monotonic() - t0)

    async def stop_speaking() -> None:
        nonlocal play_task
        if play_task and not play_task.done():
            play_task.cancel()
            await asyncio.gather(play_task, return_exceptions=True)
        await send_event({"event": "clear", "streamSid": stream_sid})

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "start":
                stream_sid = msg.get("start", {}).get("streamSid") or msg.get("streamSid")
                logger.info("call started (streamSid=%s)", stream_sid)
                await speak(GREETING)
                continue
            if event == "stop":
                logger.info("call stopped")
                break
            if event != "media":
                continue

            payload = msg.get("media", {}).get("payload")
            if not payload:
                continue
            pcm = audioop.ulaw2lin(base64.b64decode(payload), 2)
            rms = audioop.rms(pcm, 2)
            voiced = rms >= SPEECH_RMS

            if speaking:
                # barge-in: sustained caller speech cuts off the agent
                barge_ms = barge_ms + FRAME_MS if voiced else 0
                if barge_ms >= BARGE_IN_MS:
                    logger.info("barge-in detected")
                    await stop_speaking()
                    barge_ms = 0
                    buf.clear(); buf.extend(pcm); seen_speech = True; silence_ms = 0; voiced_ms = FRAME_MS
                continue

            # listening
            buf.extend(pcm)
            if voiced:
                seen_speech = True; voiced_ms += FRAME_MS; silence_ms = 0
            else:
                silence_ms += FRAME_MS

            too_long = len(buf) >= MAX_UTTERANCE_MS * TW_RATE * 2 // 1000
            endpointed = (
                seen_speech and voiced_ms >= 120 and silence_ms >= ENDPOINT_MS
                and len(buf) >= MIN_UTTERANCE_MS * TW_RATE * 2 // 1000
            )
            busy = turn_task is not None and not turn_task.done()
            if (endpointed or too_long) and not busy:
                pcm8k = bytes(buf)
                buf.clear(); seen_speech = False; silence_ms = 0; voiced_ms = 0
                turn_task = asyncio.create_task(run_turn(pcm8k))
            elif not seen_speech and len(buf) > TW_RATE * 2:  # keep a rolling 1s of pre-silence only
                del buf[:-TW_RATE * 2]
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("call failed")
    finally:
        for task in (play_task, turn_task):
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        logger.info("call closed")
