"""Local "phone call" simulator — the Twilio bypass.

Speaks the exact Twilio Media Streams WebSocket protocol against call_agent's
/twilio/ws endpoint, so you can place a full end-to-end call with NO Twilio
account. It synthesizes a spoken question with your local Kokoro voice, streams
it like a caller would, then records everything the agent says back to a WAV
you can listen to.

Usage:
  .venv312/bin/python services/telephony/simulate_call.py \
      --question "What services do you offer and what are your hours?"

Then open services/telephony/last_call.wav to hear the agent's greeting + answer.
"""

from __future__ import annotations

import argparse
import asyncio
import audioop
import base64
import json
import os
import wave
from pathlib import Path

import numpy as np
import websockets
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parents[2]
TW_RATE = 8000
FRAME_BYTES = 160  # 20 ms of 8 kHz mu-law
SID = "MZsimulated0000000000000000000000"


def synth_question_ulaw(text: str, voice: str, lang: str) -> bytes:
    model = Kokoro(str(ROOT / "models" / "kokoro-v1.0.onnx"), str(ROOT / "models" / "voices-v1.0.bin"))
    samples, rate = model.create(text, voice=voice, speed=1.0, lang=lang)
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1, 1) * 32767).astype("<i2").tobytes()
    pcm8k, _ = audioop.ratecv(pcm, 2, 1, int(rate), TW_RATE, None)
    return audioop.lin2ulaw(pcm8k, 2)


async def run(url: str, question: str, voice: str, lang: str, out: Path) -> None:
    print(f"Synthesizing caller question with Kokoro ({voice})...")
    ulaw = synth_question_ulaw(question, voice, lang)
    frames = [ulaw[i:i + FRAME_BYTES] for i in range(0, len(ulaw), FRAME_BYTES)]
    print(f"Caller question: {question!r}  ({len(frames) * 20} ms)")

    out_pcm = bytearray()           # everything the agent says (greeting + answer), PCM16 @8k
    greeting_done = asyncio.Event()
    answer_done = asyncio.Event()
    question_sent = asyncio.Event()

    async with websockets.connect(url, max_size=None) as ws:
        async def receiver() -> None:
            async for raw in ws:
                msg = json.loads(raw)
                event = msg.get("event")
                if event == "media":
                    payload = msg.get("media", {}).get("payload")
                    if payload:
                        out_pcm.extend(audioop.ulaw2lin(base64.b64decode(payload), 2))
                elif event == "mark":
                    if not question_sent.is_set():
                        greeting_done.set()      # agent finished the greeting
                    else:
                        answer_done.set()        # agent finished answering

        recv_task = asyncio.create_task(receiver())

        await ws.send(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
        await ws.send(json.dumps({
            "event": "start", "sequenceNumber": "1", "streamSid": SID,
            "start": {"streamSid": SID, "accountSid": "ACsim", "callSid": "CAsim",
                      "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": TW_RATE, "channels": 1}},
        }))

        print("Waiting for the agent's greeting...")
        try:
            await asyncio.wait_for(greeting_done.wait(), timeout=45)
        except asyncio.TimeoutError:
            print("(no greeting mark yet — continuing anyway)")

        async def send_frame(payload: bytes) -> None:
            await ws.send(json.dumps({"event": "media", "streamSid": SID,
                                      "media": {"payload": base64.b64encode(payload).decode("ascii")}}))

        print("Caller speaking...")
        for frame in frames:
            await send_frame(frame)
            await asyncio.sleep(0.02)
        # trailing silence so the agent's endpointer knows the caller stopped
        silence = b"\xff" * FRAME_BYTES  # mu-law silence
        for _ in range(60):  # 1.2 s
            await send_frame(silence)
            await asyncio.sleep(0.02)
        question_sent.set()

        print("Waiting for the agent's answer (CPU inference, be patient)...")
        try:
            await asyncio.wait_for(answer_done.wait(), timeout=90)
        except asyncio.TimeoutError:
            print("(timed out waiting for answer mark — saving what we have)")
        await asyncio.sleep(0.3)
        recv_task.cancel()

    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(TW_RATE)
        wav.writeframes(bytes(out_pcm))
    secs = len(out_pcm) / (TW_RATE * 2)
    print(f"\nSaved agent audio ({secs:.1f}s) to {out}")
    print("Open that WAV to hear the greeting + answer. Transcript + reply text are in the server log.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a Twilio Media Streams call locally.")
    parser.add_argument("--url", default=os.getenv("VOLVOX_WS_URL", "ws://127.0.0.1:8080/twilio/ws"))
    parser.add_argument("--question", default="What services do you offer, and what are your hours?")
    parser.add_argument("--voice", default=os.getenv("VOLVOX_CALLER_VOICE", "am_michael"))
    parser.add_argument("--lang", default="en-us")
    parser.add_argument("--out", type=Path, default=ROOT / "services" / "telephony" / "last_call.wav")
    args = parser.parse_args()
    asyncio.run(run(args.url, args.question, args.voice, args.lang, args.out))


if __name__ == "__main__":
    main()
