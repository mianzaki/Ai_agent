"""Exercise the installed Pipecat Silero VAD against a WAV and silence control."""

import argparse
import asyncio
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams, VADState


SAMPLE_RATE = 16000
FRAME_SAMPLES = 512


async def analyze(samples: np.ndarray) -> list[VADState]:
    analyzer = SileroVADAnalyzer(
        sample_rate=SAMPLE_RATE,
        params=VADParams(
            confidence=0.72, start_secs=0.16, stop_secs=0.6, min_volume=0.35
        ),
    )
    analyzer.set_sample_rate(SAMPLE_RATE)
    states = []
    padded = np.pad(samples, (SAMPLE_RATE // 2, SAMPLE_RATE))
    for start in range(0, len(padded) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        frame = np.clip(
            padded[start : start + FRAME_SAMPLES] * 32768.0, -32768, 32767
        ).astype(np.int16)
        states.append(await analyzer.analyze_audio(frame.tobytes()))
    return states


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", required=True, type=Path, help="Speech-containing WAV")
    args = parser.parse_args()
    if not args.wav.is_file():
        parser.error(f"WAV not found: {args.wav}")
    try:
        audio, sample_rate = sf.read(str(args.wav), dtype="float32", always_2d=True)
        if not np.isfinite(audio).all() or audio.size == 0:
            raise ValueError("WAV is empty or contains invalid samples")
        mono = audio.mean(axis=1)
        mono = soxr.resample(mono, sample_rate, SAMPLE_RATE)

        speech_states = await analyze(mono)
        silence_states = await analyze(np.zeros(SAMPLE_RATE * 2, dtype=np.float32))
        if VADState.SPEAKING not in speech_states:
            raise AssertionError("Silero did not detect speech in the provided WAV")
        if speech_states[-1] != VADState.QUIET:
            raise AssertionError("Silero did not return to QUIET after trailing silence")
        if any(s in (VADState.STARTING, VADState.SPEAKING) for s in silence_states):
            raise AssertionError("Silero triggered on the all-silence control")
        print(
            f"Pipecat Silero VAD passed: speech detected, trailing silence returned "
            f"to QUIET, silence control stayed quiet ({len(speech_states)} frames)."
        )
        return 0
    except Exception as exc:
        print(f"Silero VAD test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
