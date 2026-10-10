"""Test Windows microphone access or transcribe a prerecorded WAV locally."""

import argparse
import re
import sys
from pathlib import Path

from local_speech import (
    DEFAULT_WHISPER_MODEL,
    check_microphone_stream,
    inspect_wav,
    list_input_devices,
    load_whisper_model,
    record_until_enter,
    transcribe_wav,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_RECORDING = ROOT / "artifacts" / "microphone-test.wav"


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.casefold()).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--list-devices", action="store_true", help="Enumerate Windows input devices."
    )
    mode.add_argument(
        "--mic-check",
        action="store_true",
        help="Open the default/input mic briefly without saving audio.",
    )
    mode.add_argument(
        "--record", action="store_true", help="Record until Enter, then transcribe."
    )
    mode.add_argument("--wav", type=Path, help="Transcribe an existing audio file.")
    parser.add_argument("--device", type=int, help="Input device index from --list-devices.")
    parser.add_argument("--output", type=Path, default=DEFAULT_RECORDING)
    parser.add_argument("--model", default=DEFAULT_WHISPER_MODEL)
    parser.add_argument(
        "--expect",
        help="Optional case-insensitive phrase required in the recognized transcript.",
    )
    args = parser.parse_args()

    try:
        if args.list_devices:
            devices = list_input_devices()
            print(f"Found {len(devices)} microphone/input device(s).")
            return 0

        if args.mic_check:
            devices = list_input_devices()
            selected = args.device
            if selected is not None and all(d["index"] != selected for d in devices):
                raise ValueError(f"Device index {selected} is not an input device.")
            check_microphone_stream(selected)
            return 0

        audio_path = args.wav
        if args.record:
            # Enumerate up front to give useful device/rate/channel information.
            devices = list_input_devices()
            selected = args.device
            if selected is not None and all(d["index"] != selected for d in devices):
                raise ValueError(f"Device index {selected} is not an input device.")
            if selected is None:
                selected = next((d["index"] for d in devices if d["default"]), None)
                if selected is None:
                    selected = devices[0]["index"]
            record_until_enter(args.output, selected)
            audio_path = args.output

        if audio_path is None:
            raise ValueError("Provide --record or --wav PATH.")
        # Validate the recording before loading/downloading Whisper so silent or
        # malformed files can be diagnosed independently of model availability.
        inspect_wav(audio_path)
        model = load_whisper_model(args.model)
        transcript, stats = transcribe_wav(model, audio_path)
        print(
            f"Input audio: {stats.duration_seconds:.2f}s, {stats.sample_rate} Hz, "
            f"{stats.channels} channel(s), peak={stats.peak:.4f}, rms={stats.rms:.4f}"
        )
        print(f"Transcript: {transcript}")
        if args.expect and normalize(args.expect) not in normalize(transcript):
            print(f"Expected phrase was not found: {args.expect!r}", file=sys.stderr)
            return 1
        return 0
    except KeyboardInterrupt:
        print("STT test cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"STT test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
