"""Generate and validate a local Kokoro ONNX WAV sample."""

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro


ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / "models" / "kokoro-v1.0.onnx"
DEFAULT_VOICES = ROOT / "models" / "voices-v1.0.bin"
DEFAULT_OUTPUT = ROOT / "artifacts" / "kokoro-test.wav"


def generate_and_validate(
    model_path: Path, voices_path: Path, output_path: Path, text: str
) -> tuple[int, float]:
    for label, path in (("Kokoro model", model_path), ("Kokoro voices", voices_path)):
        if not path.is_file():
            raise FileNotFoundError(
                f"{label} file not found: {path}. See SETUP.md for the official download URL."
            )

    kokoro = Kokoro(str(model_path), str(voices_path))
    samples, sample_rate = kokoro.create(
        text, voice="af_sarah", speed=1.0, lang="en-us"
    )
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0 or not np.isfinite(samples).all():
        raise RuntimeError("Kokoro returned empty or invalid audio samples.")
    peak = float(np.max(np.abs(samples)))
    if peak <= 1e-5:
        raise RuntimeError("Kokoro returned silent audio.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), samples, sample_rate, subtype="PCM_16", format="WAV")

    saved_audio, saved_rate = sf.read(str(output_path), dtype="float32")
    if saved_audio.size == 0 or not np.isfinite(saved_audio).all():
        raise RuntimeError("Generated WAV is empty or contains invalid samples.")
    saved_peak = float(np.max(np.abs(saved_audio)))
    if saved_peak <= 1e-5:
        raise RuntimeError("Generated WAV contains only silence.")
    if saved_rate != sample_rate:
        raise RuntimeError(
            f"WAV sample rate mismatch: expected {sample_rate}, got {saved_rate}."
        )
    return saved_rate, saved_peak


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--voices", type=Path, default=DEFAULT_VOICES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--text", default="Hello, this is a local Kokoro speech test."
    )
    args = parser.parse_args()
    try:
        sample_rate, peak = generate_and_validate(
            args.model, args.voices, args.output, args.text
        )
    except Exception as exc:
        print(f"Kokoro TTS test failed: {exc}")
        return 1
    print(
        f"Kokoro generated and validated {args.output} "
        f"({sample_rate} Hz, peak amplitude {peak:.4f})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
