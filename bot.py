"""Minimal local Volvox text agent backed by Ollama through Pipecat."""

import argparse
import asyncio
import sys
from pathlib import Path

from services.voice.volvox_voice.agent import (
    KOKORO_MODEL,
    KOKORO_VOICES,
    MAX_HISTORY_TURNS,
    OLLAMA_BASE_URL,
    PrintResponse,
    WavWriter,
    run_agent,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_WAV = ROOT / "artifacts" / "volvox-response.wav"
DEFAULT_INPUT_WAV = ROOT / "artifacts" / "push-to-talk-input.wav"


def play_response(path: Path) -> None:
    """Play the completed WAV through the default Windows output device."""
    try:
        import winsound

        winsound.PlaySound(str(path.resolve()), winsound.SND_FILENAME)
    except Exception as exc:
        raise RuntimeError(
            f"Could not play response audio on the default Windows device: {exc}"
        ) from exc


async def run_push_to_talk(args, tts_enabled: bool, playback_enabled: bool) -> int:
    from local_speech import (
        DEFAULT_WHISPER_MODEL,
        list_input_devices,
        load_whisper_model,
        record_until_enter,
        transcribe_wav,
    )

    try:
        devices = list_input_devices()
    except Exception as exc:
        print(f"Microphone unavailable: {exc}", file=sys.stderr)
        return 1
    selected_device = args.mic_device
    if selected_device is not None and all(
        device["index"] != selected_device for device in devices
    ):
        print(f"Device {selected_device} is not an input device.", file=sys.stderr)
        return 1
    if selected_device is None:
        selected_device = next(
            (device["index"] for device in devices if device["default"]),
            devices[0]["index"],
        )

    try:
        whisper = load_whisper_model(args.whisper_model or DEFAULT_WHISPER_MODEL)
    except Exception as exc:
        print(f"Speech recognition unavailable: {exc}", file=sys.stderr)
        return 1

    history: list[dict[str, str]] = []
    turn = 0
    print("Push-to-talk ready. Enter starts a recording; Enter again stops it; type q to quit.")
    while args.max_turns <= 0 or turn < args.max_turns:
        try:
            command = input("\n[Enter] record, [q] quit: ").strip().casefold()
        except (EOFError, KeyboardInterrupt):
            print("\nPush-to-talk stopped.")
            return 0
        if command in {"q", "quit", "exit"}:
            break

        try:
            record_until_enter(args.recording_wav, selected_device)
            transcript, stats = transcribe_wav(whisper, args.recording_wav)
        except KeyboardInterrupt:
            print("\nRecording cancelled.")
            continue
        except Exception as exc:
            print(f"Speech input failed: {exc}", file=sys.stderr)
            continue

        print(
            f"Recognized ({stats.sample_rate} Hz, {stats.channels} channel): "
            f"{transcript}"
        )
        turn += 1
        turn_wav = args.output_wav.with_name(
            f"{args.output_wav.stem}-turn-{turn:02d}{args.output_wav.suffix or '.wav'}"
        )
        try:
            response, wav_writer = await run_agent(
                transcript,
                tts_enabled=tts_enabled,
                output_wav=turn_wav,
                voice=args.voice,
                history=history,
            )
        except Exception as exc:
            print(f"Assistant turn failed: {exc}", file=sys.stderr)
            continue
        if not response:
            print("Assistant returned no text; the turn was not added to history.", file=sys.stderr)
            continue

        history.extend(
            [
                {"role": "user", "content": transcript},
                {"role": "assistant", "content": response},
            ]
        )
        history = history[-(MAX_HISTORY_TURNS * 2) :]

        if tts_enabled:
            if wav_writer is None or wav_writer.error or wav_writer.audio_frames == 0:
                print(
                    f"Speech synthesis failed: "
                    f"{wav_writer.error if wav_writer and wav_writer.error else 'no audio frames'}",
                    file=sys.stderr,
                )
                continue
            print(f"Response WAV saved: {turn_wav}")
            if playback_enabled:
                try:
                    play_response(turn_wav)
                except Exception as exc:
                    print(f"Speaker playback failed: {exc}", file=sys.stderr)

    return 0


async def run_audio_file(args, tts_enabled: bool, playback_enabled: bool) -> int:
    """Run one recorded WAV through local Whisper, Ollama, and optional Kokoro."""
    from local_speech import load_whisper_model, transcribe_wav

    try:
        whisper = load_whisper_model(args.whisper_model)
        transcript, stats = transcribe_wav(whisper, args.audio_file)
    except Exception as exc:
        print(f"Audio-file speech input failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Recognized ({stats.sample_rate} Hz, {stats.channels} channel): {transcript}"
    )
    try:
        response, wav_writer = await run_agent(
            transcript,
            tts_enabled=tts_enabled,
            output_wav=args.output_wav,
            voice=args.voice,
        )
    except Exception as exc:
        print(f"Assistant turn failed: {exc}", file=sys.stderr)
        return 1
    if not response:
        print("Ollama returned no text response.", file=sys.stderr)
        return 1
    if tts_enabled:
        if wav_writer is None or wav_writer.error or wav_writer.audio_frames == 0:
            reason = (
                wav_writer.error or "No audio frames were produced."
                if wav_writer
                else "No audio frames were produced."
            )
            print(f"Kokoro speech synthesis failed: {reason}", file=sys.stderr)
            return 1
        print(f"Kokoro speech saved to {args.output_wav}")
        if playback_enabled:
            try:
                play_response(args.output_wav)
            except Exception as exc:
                print(f"Speaker playback failed: {exc}", file=sys.stderr)
    return 0


async def run_realtime(args, tts_enabled: bool, playback_enabled: bool) -> int:
    """Keep one microphone stream open and submit Silero-completed turns."""
    from local_speech import (
        DEFAULT_WHISPER_MODEL,
        capture_realtime_utterance,
        list_input_devices,
        load_whisper_model,
    )

    try:
        devices = list_input_devices()
    except Exception as exc:
        print(f"Microphone unavailable: {exc}", file=sys.stderr)
        return 1
    selected = args.mic_device
    if selected is not None and all(device["index"] != selected for device in devices):
        print(f"Device {selected} is not an input device.", file=sys.stderr)
        return 1
    if selected is None:
        selected = next(
            (device["index"] for device in devices if device["default"]),
            devices[0]["index"],
        )
    try:
        whisper = load_whisper_model(args.whisper_model or DEFAULT_WHISPER_MODEL)
    except Exception as exc:
        print(f"Speech recognition unavailable: {exc}", file=sys.stderr)
        return 1

    history: list[dict[str, str]] = []
    turn = 0

    async def handle_utterance(audio, stats, _speech_end_delay):
        nonlocal turn, history
        try:
            segments, _info = whisper.transcribe(
                audio.astype("float32") / 32768.0,
                language="en",
                beam_size=5,
                vad_filter=False,
            )
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            print(f"Whisper transcription failed: {exc}", file=sys.stderr)
            return
        if not transcript:
            print("Whisper returned no speech; ignoring this segment.", file=sys.stderr)
            return

        print(f"Recognized: {transcript}")
        turn += 1
        turn_wav = args.output_wav.with_name(
            f"{args.output_wav.stem}-realtime-{turn:02d}"
            f"{args.output_wav.suffix or '.wav'}"
        )
        try:
            response, wav_writer = await run_agent(
                transcript,
                tts_enabled=tts_enabled,
                output_wav=turn_wav,
                voice=args.voice,
                history=history,
            )
        except Exception as exc:
            print(f"Assistant turn failed: {exc}", file=sys.stderr)
            return
        if not response:
            print("Assistant returned no text; turn was not saved.", file=sys.stderr)
            return

        history.extend(
            [
                {"role": "user", "content": transcript},
                {"role": "assistant", "content": response},
            ]
        )
        history = history[-(MAX_HISTORY_TURNS * 2) :]

        if tts_enabled:
            if wav_writer is None or wav_writer.error or wav_writer.audio_frames == 0:
                detail = wav_writer.error if wav_writer else "No audio frames were produced."
                print(f"Kokoro speech synthesis failed: {detail}", file=sys.stderr)
            else:
                print(f"Response WAV saved: {turn_wav}")
                if playback_enabled:
                    try:
                        play_response(turn_wav)
                    except Exception as exc:
                        print(f"Speaker playback failed: {exc}", file=sys.stderr)
        print(f"Turn {turn} complete (captured segment: {stats.duration_seconds:.2f}s).")

    try:
        await capture_realtime_utterance(
            selected,
            silence_timeout_seconds=args.vad_silence,
            min_rms=args.vad_min_rms,
            on_utterance=handle_utterance,
        )
    except Exception as exc:
        print(f"Realtime audio failed: {exc}", file=sys.stderr)
        return 1
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Volvox text agent.")
    parser.add_argument(
        "--mode",
        choices=("text", "audio-file", "push-to-talk", "realtime"),
        default="text",
        help="text sends --prompt; audio-file transcribes WAV; push-to-talk records manually; realtime uses Silero VAD.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Send a short prompt and fail unless Pipecat receives generated text.",
    )
    parser.add_argument(
        "--tts",
        choices=("on", "off"),
        default=None,
        help="Enable or disable Kokoro TTS; defaults off in text mode, on in speech modes.",
    )
    parser.add_argument("--voice", default="af_sarah", help="Kokoro voice name.")
    parser.add_argument(
        "--output-wav",
        type=Path,
        default=DEFAULT_WAV,
        help="Destination for generated speech WAV.",
    )
    parser.add_argument("--whisper-model", default="base.en", help="Local faster-whisper model.")
    parser.add_argument("--mic-device", type=int, help="Input index shown by test_stt.py --list-devices.")
    parser.add_argument("--recording-wav", type=Path, default=DEFAULT_INPUT_WAV)
    parser.add_argument(
        "--vad-silence", type=float, default=1.2,
        help="Seconds of silence before a realtime utterance is submitted.",
    )
    parser.add_argument(
        "--vad-min-rms", type=float, default=0.004,
        help="Minimum normalized RMS energy required for a realtime utterance.",
    )
    parser.add_argument(
        "--audio-file",
        type=Path,
        help="Existing WAV for --mode audio-file; useful for microphone-independent tests.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=0,
        help="Stop push-to-talk after this many turns; 0 keeps the bounded-history session open.",
    )
    parser.add_argument(
        "--playback",
        choices=("on", "off"),
        default=None,
        help="Play TTS responses on the default Windows output device.",
    )
    parser.add_argument(
        "--prompt",
        default="Hello! Introduce yourself in two sentences.",
        help="Text to send to the local model.",
    )
    args = parser.parse_args()
    if args.vad_silence <= 0 or args.vad_min_rms < 0:
        parser.error("--vad-silence must be positive and --vad-min-rms cannot be negative")
    speech_mode = args.mode in {"audio-file", "push-to-talk", "realtime"}
    tts_enabled = args.tts == "on" if args.tts is not None else speech_mode
    playback_enabled = (
        args.playback == "on"
        if args.playback is not None
        else args.mode in {"push-to-talk", "realtime"} and tts_enabled
    )
    if args.mode == "push-to-talk":
        return await run_push_to_talk(args, tts_enabled, playback_enabled)
    if args.mode == "realtime":
        return await run_realtime(args, tts_enabled, playback_enabled)
    if args.mode == "audio-file":
        if args.audio_file is None:
            parser.error("--mode audio-file requires --audio-file PATH")
        return await run_audio_file(args, tts_enabled, playback_enabled)

    prompt = "Reply with exactly: Volvox local agent is ready." if args.smoke_test else args.prompt

    print("Starting Volvox AI Agent (local Ollama)...")
    try:
        response, wav_writer = await run_agent(
            prompt,
            tts_enabled=tts_enabled,
            output_wav=args.output_wav,
            voice=args.voice,
        )
    except Exception as exc:
        print(f"Agent failed: {exc}", file=sys.stderr)
        return 1

    if not response:
        print("Agent failed: Ollama returned no text response.", file=sys.stderr)
        return 1
    if args.smoke_test:
        print("Smoke test passed: Pipecat received a non-empty Ollama response.")
    if tts_enabled:
        if wav_writer is None or wav_writer.error or wav_writer.audio_frames == 0:
            reason = (
                wav_writer.error or "No audio frames were produced."
                if wav_writer
                else "No audio frames were produced."
            )
            print(f"TTS failed: {reason}", file=sys.stderr)
            return 1
        print(f"Kokoro speech saved to {args.output_wav}")
    print("Agent finished.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nVolvox agent stopped.")
        raise SystemExit(130)
