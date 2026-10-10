"""Play a previously generated WAV file on the default Windows audio device."""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path, help="Path to a WAV file to play")
    args = parser.parse_args()
    if not args.wav.is_file():
        print(f"WAV file not found: {args.wav}", file=sys.stderr)
        return 1
    try:
        import winsound

        winsound.PlaySound(str(args.wav.resolve()), winsound.SND_FILENAME)
    except Exception as exc:
        print(
            f"Could not play WAV on the default Windows audio device: {exc}",
            file=sys.stderr,
        )
        return 1
    print(f"Playback finished: {args.wav}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
