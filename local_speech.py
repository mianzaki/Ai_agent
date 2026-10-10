"""Local WAV recording and faster-whisper helpers for Windows push-to-talk."""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

import numpy as np
import sounddevice as sd
import soundfile as sf

if TYPE_CHECKING:
    from faster_whisper import WhisperModel


ROOT = Path(__file__).resolve().parent
WHISPER_CACHE = ROOT / "models" / "whisper"
DEFAULT_WHISPER_MODEL = "base.en"
SILENCE_PEAK_THRESHOLD = 1e-5
REALTIME_SAMPLE_RATE = 16000
REALTIME_FRAME_SAMPLES = 512


@dataclass
class AudioStats:
    sample_rate: int
    channels: int
    duration_seconds: float
    peak: float
    rms: float


def list_input_devices() -> list[dict]:
    """Print and return Windows/PortAudio input devices."""
    try:
        devices = sd.query_devices()
        default_input = sd.default.device[0]
    except Exception as exc:
        raise RuntimeError(
            "Could not enumerate audio devices through PortAudio. Check that the "
            "Windows audio service and microphone driver are available. "
            f"Details: {exc}"
        ) from exc

    inputs = []
    for index, device in enumerate(devices):
        channels = int(device.get("max_input_channels", 0))
        if channels <= 0:
            continue
        row = {
            "index": index,
            "name": device.get("name", "Unknown device"),
            "channels": channels,
            "sample_rate": int(round(device.get("default_samplerate", 0))),
            "default": index == default_input,
        }
        inputs.append(row)
        suffix = " (default)" if row["default"] else ""
        print(
            f"[{index}] {row['name']}{suffix}: {channels} input channels, "
            f"default rate {row['sample_rate']} Hz"
        )

    if not inputs:
        raise RuntimeError(
            "No microphone/input device was found. Connect or enable a microphone, "
            "then check Windows Settings > Privacy & security > Microphone."
        )
    return inputs


def _mic_permission_hint(exc: Exception) -> RuntimeError:
    return RuntimeError(
        "Could not open the microphone. Check Windows Settings > Privacy & security > "
        "Microphone, allow desktop apps to access the microphone, close other apps "
        f"using it, and verify the selected device. Details: {exc}"
    )


def record_until_enter(output_path: Path, device: int | None = None) -> AudioStats:
    """Record mono audio from the selected/default input until Enter is pressed."""
    try:
        if device is None:
            device = sd.default.device[0]
        if device is None or device < 0:
            raise RuntimeError("Windows has no default microphone selected.")
        device_info = sd.query_devices(device, "input")
        if int(device_info.get("max_input_channels", 0)) < 1:
            raise RuntimeError(f"Input device {device} has no input channels.")
        sample_rate = int(round(device_info.get("default_samplerate", 0)))
        if sample_rate <= 0:
            raise RuntimeError(f"Input device {device} reported an invalid sample rate.")
    except Exception as exc:
        raise _mic_permission_hint(exc) from exc

    chunks: list[np.ndarray] = []
    stream_status: list[str] = []
    lock = threading.Lock()

    def callback(indata, _frames, _time_info, status):
        if status:
            stream_status.append(str(status))
        with lock:
            chunks.append(indata.copy())

    print(
        f"Recording from [{device}] {device_info['name']} at {sample_rate} Hz, mono. "
        "Speak now; press Enter to stop."
    )
    try:
        with sd.InputStream(
            device=device,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            callback=callback,
        ):
            input()
    except KeyboardInterrupt:
        print("\nRecording cancelled.")
        raise
    except Exception as exc:
        raise _mic_permission_hint(exc) from exc

    with lock:
        if not chunks:
            raise RuntimeError("The microphone stream returned no audio samples.")
        audio = np.concatenate(chunks, axis=0).reshape(-1)

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    if audio.size == 0 or peak <= SILENCE_PEAK_THRESHOLD:
        raise RuntimeError(
            "The recording is silent. Check the microphone mute switch, selected "
            "input device, input level, and Windows microphone permission."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), audio, sample_rate, subtype="PCM_16", format="WAV")
    duration = audio.size / sample_rate
    if stream_status:
        print(f"Audio stream notice: {'; '.join(sorted(set(stream_status)))}")
    stats = AudioStats(sample_rate, 1, duration, peak, rms)
    print(
        f"Saved {output_path}: {duration:.2f}s, {stats.sample_rate} Hz, "
        f"{stats.channels} channel, peak={peak:.4f}, rms={rms:.4f}"
    )
    return stats


def check_microphone_stream(device: int | None = None) -> AudioStats:
    """Open the microphone briefly and capture in memory without writing a file."""
    try:
        if device is None:
            device = sd.default.device[0]
        if device is None or device < 0:
            raise RuntimeError("Windows has no default microphone selected.")
        device_info = sd.query_devices(device, "input")
        if int(device_info.get("max_input_channels", 0)) < 1:
            raise RuntimeError(f"Input device {device} has no input channels.")
        sample_rate = int(round(device_info.get("default_samplerate", 0)))
        if sample_rate <= 0:
            raise RuntimeError(f"Input device {device} reported an invalid sample rate.")
    except Exception as exc:
        raise _mic_permission_hint(exc) from exc

    captured: list[np.ndarray] = []

    def callback(indata, _frames, _time_info, _status):
        captured.append(indata.copy())

    try:
        with sd.InputStream(
            device=device,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            callback=callback,
        ):
            time.sleep(0.5)
    except Exception as exc:
        raise _mic_permission_hint(exc) from exc

    if not captured:
        raise RuntimeError("Microphone opened, but returned no input samples.")
    audio = np.concatenate(captured, axis=0).reshape(-1)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    stats = AudioStats(sample_rate, 1, audio.size / sample_rate, peak, rms)
    print(
        f"Microphone stream opened and captured {stats.duration_seconds:.2f}s "
        f"in memory: {stats.sample_rate} Hz, {stats.channels} channel, "
        f"peak={peak:.4f}, rms={rms:.4f}. No audio file was saved."
    )
    if peak <= SILENCE_PEAK_THRESHOLD:
        print(
            "Input was silent during the short check; confirm the microphone is "
            "unmuted and has an audible signal level."
        )
    return stats


def inspect_wav(path: Path) -> AudioStats:
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")
    try:
        audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:
        raise RuntimeError(f"Could not read WAV/audio file {path}: {exc}") from exc
    if audio.size == 0 or sample_rate <= 0:
        raise RuntimeError(f"Audio file contains no samples: {path}")
    if not np.isfinite(audio).all():
        raise RuntimeError(f"Audio file contains invalid sample values: {path}")
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if peak <= SILENCE_PEAK_THRESHOLD:
        raise RuntimeError(
            f"Audio is silent: {path}. Check the recording device/input level."
        )
    return AudioStats(
        sample_rate=sample_rate,
        channels=audio.shape[1],
        duration_seconds=audio.shape[0] / sample_rate,
        peak=peak,
        rms=rms,
    )


def load_whisper_model(model_name: str = DEFAULT_WHISPER_MODEL) -> "WhisperModel":
    """Load/download a local English Whisper model using CPU int8 inference."""
    WHISPER_CACHE.mkdir(parents=True, exist_ok=True)
    print(
        f"Loading Whisper {model_name} on CPU (int8). The first run downloads "
        "the model; later inference is local."
    )
    try:
        from faster_whisper import WhisperModel

        return WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            download_root=str(WHISPER_CACHE),
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not load Whisper model '{model_name}'. Check network access for "
            "the first model download, available disk space, and the local model "
            f"cache at {WHISPER_CACHE}. Details: {exc}"
        ) from exc


def transcribe_wav(model: "WhisperModel", path: Path) -> tuple[str, AudioStats]:
    stats = inspect_wav(path)
    try:
        segments, _info = model.transcribe(
            str(path), language="en", beam_size=5, vad_filter=True
        )
        # faster-whisper returns a lazy generator; iterate to run inference.
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as exc:
        raise RuntimeError(f"Whisper transcription failed for {path}: {exc}") from exc
    if not text:
        raise RuntimeError(
            "Whisper returned an empty transcript. The recording may contain no "
            "speech or may be too quiet/unclear."
        )
    return text, stats


async def capture_realtime_utterance(
    device: int,
    *,
    sample_rate: int = REALTIME_SAMPLE_RATE,
    min_speech_seconds: float = 0.45,
    max_utterance_seconds: float = 20.0,
    silence_timeout_seconds: float = 1.2,
    min_rms: float = 0.004,
    on_utterance: Callable[[np.ndarray, AudioStats, float], Awaitable[None]] | None = None,
):
    """Continuously read the microphone and return a Silero-delimited utterance.

    Captured audio is mono 16 kHz PCM16 so it can be passed directly to Pipecat's
    bundled Silero analyzer and faster-whisper. Returns ``(audio, stats, delay)``
    when speech ends if no handler was provided. With a handler, keep the
    microphone stream open across multiple turns and ignore captured output
    while the handler transcribes and responds.
    """
    import queue

    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams, VADState

    try:
        device_info = sd.query_devices(device, "input")
        if int(device_info.get("max_input_channels", 0)) < 1:
            raise RuntimeError(f"Input device {device} has no input channels.")
        sd.check_input_settings(
            device=device, channels=1, samplerate=sample_rate, dtype="float32"
        )
    except Exception as exc:
        raise _mic_permission_hint(exc) from exc

    # These are Pipecat 1.12.0 VADParams fields, measured on each 32 ms frame.
    analyzer = SileroVADAnalyzer(
        sample_rate=sample_rate,
        params=VADParams(
            confidence=0.72,
            start_secs=0.16,
            stop_secs=silence_timeout_seconds,
            min_volume=0.35,
        ),
    )
    analyzer.set_sample_rate(sample_rate)
    audio_queue: queue.Queue[np.ndarray | BaseException] = queue.Queue(maxsize=64)
    capture_state = {"paused": False}

    def callback(indata, _frames, _time_info, status):
        if capture_state["paused"]:
            return
        if status:
            print(f"Microphone notice: {status}", file=sys.stderr)
        try:
            audio_queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            # A growing queue means the consumer is behind; drop audio instead
            # of accumulating latency and announce the stream degradation.
            try:
                audio_queue.get_nowait()
                audio_queue.put_nowait(RuntimeError("Microphone processing overrun."))
            except queue.Empty:
                pass

    chunks: list[np.ndarray] = []
    utterance_chunks: list[np.ndarray] = []
    speaking = False
    speech_start_at: float | None = None
    speech_end_at: float | None = None
    max_samples = int(max_utterance_seconds * sample_rate)

    print(
        f"Listening continuously on [{device}] {device_info['name']} at "
        f"{sample_rate} Hz, mono. Speak naturally; Ctrl+C stops realtime mode."
    )
    try:
        with sd.InputStream(
            device=device,
            samplerate=sample_rate,
            channels=1,
            blocksize=REALTIME_FRAME_SAMPLES,
            dtype="float32",
            callback=callback,
        ):
            while True:
                try:
                    item = await asyncio.to_thread(audio_queue.get, True, 0.2)
                except queue.Empty:
                    continue
                if isinstance(item, BaseException):
                    raise item
                float_frame = item
                frame = np.clip(float_frame * 32768.0, -32768, 32767).astype(np.int16)
                state = await analyzer.analyze_audio(frame.tobytes())
                now = time.perf_counter()

                if not speaking and state in (VADState.STARTING, VADState.SPEAKING):
                    speaking = True
                    speech_start_at = now
                    utterance_chunks = [*chunks, frame]
                    chunks.clear()
                    speech_end_at = None
                    print("Speech detected.")
                elif speaking:
                    utterance_chunks.append(frame)
                    if len(utterance_chunks) >= max_samples:
                        print(
                            f"Utterance reached {max_utterance_seconds:.0f}s limit; "
                            "submit it now."
                        )
                        state = VADState.QUIET
                    if state == VADState.STOPPING and speech_end_at is None:
                        speech_end_at = now
                    if state == VADState.SPEAKING:
                        speech_end_at = None
                    if state == VADState.QUIET or len(utterance_chunks) >= max_samples:
                        if len(utterance_chunks) < max_samples:
                            utterance_chunks.append(frame)
                        audio = np.concatenate(utterance_chunks)
                        duration = audio.size / sample_rate
                        peak = float(np.max(np.abs(audio))) / 32768.0
                        rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float32))))) / 32768.0
                        speech_duration = (speech_end_at or now) - (speech_start_at or now)
                        delay = max(0.0, now - speech_end_at) if speech_end_at else 0.0
                        if duration < min_speech_seconds or rms < min_rms or peak <= SILENCE_PEAK_THRESHOLD:
                            print(
                                "Ignored short or low-energy audio "
                                f"({duration:.2f}s, RMS {rms:.4f})."
                            )
                        else:
                            stats = AudioStats(sample_rate, 1, duration, peak, rms)
                            print(f"Speech ended ({speech_duration:.2f}s); transcribing...")
                            if on_utterance is None:
                                return audio, stats, delay
                            # Keep the input stream alive but ignore speaker output
                            # and stale audio while this turn is processed.
                            capture_state["paused"] = True
                            try:
                                await on_utterance(audio, stats, delay)
                            except Exception as exc:
                                print(f"Realtime turn handler failed: {exc}", file=sys.stderr)
                            finally:
                                while True:
                                    try:
                                        audio_queue.get_nowait()
                                    except queue.Empty:
                                        break
                                capture_state["paused"] = False
                        speaking = False
                        utterance_chunks = []
                        speech_start_at = None
                        speech_end_at = None
                        chunks.clear()
                else:
                    # A small pre-roll preserves the consonant at speech onset.
                    chunks.append(frame)
                    if len(chunks) > 8:
                        chunks.pop(0)
    except KeyboardInterrupt:
        print("\nRealtime microphone stopped.")
        return None
    except Exception as exc:
        raise _mic_permission_hint(exc) from exc
