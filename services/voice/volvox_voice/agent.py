"""Reusable Ollama/Pipecat response runner, preserving the prototype pipeline."""

import asyncio
import os
import sys
import wave
from pathlib import Path

from pipecat.frames.frames import EndFrame, ErrorFrame, LLMContextFrame, LLMFullResponseEndFrame, LLMTextFrame, TTSAudioRawFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.workers.runner import WorkerRunner


ROOT = Path(__file__).resolve().parents[3]
MODEL = os.getenv("VOLVOX_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("VOLVOX_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
KOKORO_MODEL = Path(os.getenv("VOLVOX_KOKORO_MODEL", ROOT / "models" / "kokoro-v1.0.onnx"))
KOKORO_VOICES = Path(os.getenv("VOLVOX_KOKORO_VOICES", ROOT / "models" / "voices-v1.0.bin"))
MAX_HISTORY_TURNS = 8


class PrintResponse(FrameProcessor):
    def __init__(self, response_done: asyncio.Event | None, response_parts: list[str]):
        super().__init__()
        self._response_done = response_done
        self._response_parts = response_parts

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame):
            self._response_parts.append(frame.text)
            print(frame.text, end="", flush=True)
        elif isinstance(frame, LLMFullResponseEndFrame):
            print("\n\nAI response complete!")
            if self._response_done is not None:
                self._response_done.set()
        elif isinstance(frame, ErrorFrame):
            print(f"\nPipecat error: {frame.error or 'Unknown processor error'}", file=sys.stderr)
            if self._response_done is not None:
                self._response_done.set()
        await self.push_frame(frame, direction)


class WavWriter(FrameProcessor):
    def __init__(self, output_path: Path, response_done: asyncio.Event):
        super().__init__()
        self.output_path = output_path
        self.response_done = response_done
        self._wav: wave.Wave_write | None = None
        self.audio_frames = 0
        self.error: str | None = None

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSAudioRawFrame):
            try:
                if self._wav is None:
                    self.output_path.parent.mkdir(parents=True, exist_ok=True)
                    self._wav = wave.open(str(self.output_path), "wb")
                    self._wav.setnchannels(frame.num_channels)
                    self._wav.setsampwidth(2)
                    self._wav.setframerate(frame.sample_rate)
                elif self._wav.getnchannels() != frame.num_channels or self._wav.getframerate() != frame.sample_rate:
                    raise ValueError("Kokoro changed audio format during this response.")
                self._wav.writeframesraw(frame.audio)
                self.audio_frames += 1
            except Exception as exc:
                self.error = f"Could not write TTS audio to {self.output_path}: {exc}"
                print(self.error, file=sys.stderr)
                self.close()
        elif isinstance(frame, ErrorFrame):
            self.error = frame.error or "Kokoro synthesis failed."
        elif isinstance(frame, LLMFullResponseEndFrame):
            self.close()
            self.response_done.set()
        await self.push_frame(frame, direction)

    def close(self) -> None:
        if self._wav is not None:
            try:
                self._wav.close()
            except Exception as exc:
                self.error = f"Could not finish WAV file {self.output_path}: {exc}"
            finally:
                self._wav = None


async def run_agent(prompt: str, *, tts_enabled: bool = False, output_wav: Path = ROOT / "artifacts" / "volvox-response.wav", voice: str = "af_sarah", history: list[dict[str, str]] | None = None, system_instruction: str = "You are a friendly AI receptionist for Volvox Solutions.", handle_signals: bool = True) -> tuple[str, WavWriter | None]:
    """Run one bounded-context response using Pipecat 1.12.0 worker APIs."""
    response_done = asyncio.Event()
    response_parts: list[str] = []
    started = asyncio.Event()
    llm = OLLamaLLMService(settings=OLLamaLLMService.Settings(model=MODEL, system_instruction=system_instruction), base_url=OLLAMA_BASE_URL)
    messages = [
        {"role": item["role"], "content": item["content"][-4000:]}
        for item in (history or [])[-(MAX_HISTORY_TURNS * 2):]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    messages.append({"role": "user", "content": prompt[-4000:]})
    processors: list[FrameProcessor] = [llm, PrintResponse(None if tts_enabled else response_done, response_parts)]
    writer: WavWriter | None = None
    if tts_enabled:
        missing = [str(path) for path in (KOKORO_MODEL, KOKORO_VOICES) if not path.is_file()]
        if missing:
            raise FileNotFoundError("Kokoro model/voice file missing: " + ", ".join(missing))
        from pipecat.services.kokoro.tts import KokoroTTSService
        from pipecat.transcriptions.language import Language
        tts = KokoroTTSService(model_path=str(KOKORO_MODEL), voices_path=str(KOKORO_VOICES), settings=KokoroTTSService.Settings(voice=voice, language=Language.EN, speed=1.0), sample_rate=24000)
        writer = WavWriter(output_wav, response_done)
        processors.extend([tts, writer])

    worker = PipelineWorker(Pipeline(processors), idle_timeout_secs=None)
    runner = WorkerRunner(handle_sigint=handle_signals, handle_sigterm=False)

    @worker.event_handler("on_pipeline_started")
    async def send_prompt(_worker, _frame):
        await worker.queue_frame(LLMContextFrame(LLMContext(messages)))
        started.set()

    @worker.event_handler("on_pipeline_error")
    async def report_error(_worker, frame):
        print(f"Pipeline error: {frame.error}", file=sys.stderr)
        response_done.set()

    await runner.add_workers(worker)

    async def finish_response():
        await started.wait()
        await response_done.wait()
        await worker.queue_frame(EndFrame())

    end_task = asyncio.create_task(finish_response())
    try:
        await runner.run()
    except Exception as exc:
        raise RuntimeError(f"Could not run Pipecat with local Ollama at {OLLAMA_BASE_URL}: {exc}") from exc
    finally:
        if not end_task.done():
            end_task.cancel()
        await asyncio.gather(end_task, return_exceptions=True)
        if writer is not None:
            writer.close()
    return "".join(response_parts).strip(), writer
