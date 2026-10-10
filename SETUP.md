# Volvox local voice agent: setup and compatibility

## Current status

The repository contains a local agent in `bot.py`. Text mode sends a context frame through Pipecat 1.12.0 to local Ollama. Optional Kokoro TTS speaks responses and saves WAV audio. Push-to-talk records one utterance at a time, transcribes it locally with faster-whisper, then sends the recognized text through the existing Pipecat/Ollama/Kokoro path. Conversation context keeps at most eight recent turns.

The existing `.venv` is Python 3.14.7 and has Pipecat 1.12.0 installed. The separate `.venv312` is Python 3.12.10 and holds the TTS/STT dependencies. Kokoro, faster-whisper, PyAV, and sounddevice are installed only in `.venv312`; `.venv` remains unchanged.

The `services/`, `apps/`, `packages/`, `infra/`, and `docs/` directories now contain an additive platform scaffold. Continue to use the commands below for the original CLI. See `README.md` for API scaffold instructions and `docs/architecture.md` for the audit and target design. The API is not yet authenticated or ready for production exposure.

## Windows installation

Install Python 3.12 (64-bit) alongside the existing Python installation. From PowerShell, in this project folder:

```powershell
# Create this only if .venv312 does not already exist.
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --index-url https://pypi.org/simple -r requirements-speech.txt
```

`requirements.txt` holds the minimal Pipecat text-agent dependency. `requirements-tts.txt` adds Kokoro. `requirements-speech.txt` includes the TTS set and adds faster-whisper and sounddevice. Install the speech file into `.venv312`; do not install it into `.venv`.

If PyPI access is unavailable, download wheels on a connected machine and install with `python -m pip install --no-index --find-links PATH -r requirements-speech.txt`.

The speech dependency set pins `faster-whisper==1.2.1`, `sounddevice==0.5.6`, and `av==16.0.0`. PyAV 16.0.0 is a Windows Python 3.12 wheel and loaded successfully here. PyAV 19.0.1's Windows resampler extension was blocked by this machine's Application Control policy. Keep the compatible PyAV pin when reinstalling this environment.

### Kokoro model and voices

Download the two files from the official `thewh1teagle/kokoro-onnx` GitHub release into the project `models` folder. PowerShell commands:

```powershell
New-Item -ItemType Directory -Force .\models | Out-Null
Invoke-WebRequest "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx" -OutFile .\models\kokoro-v1.0.onnx
Invoke-WebRequest "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin" -OutFile .\models\voices-v1.0.bin
```

The full-precision ONNX model is about **310 MB** and the voice pack is about **28 MB** (release-reported sizes). The Kokoro-82M model weights are Apache-2.0 licensed; the ONNX export/inference project is MIT licensed. The Kokoro package installs `espeakng-loader` for phonemization, which distributes eSpeak NG (GPL-3.0-or-later). Review and retain the applicable notices before redistribution or commercial packaging.

References: [official ONNX release assets and sizes](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0), [Kokoro-82M model card and license](https://huggingface.co/hexgrad/Kokoro-82M), [Kokoro ONNX MIT license](https://github.com/thewh1teagle/kokoro-onnx/blob/main/LICENSE), and [eSpeak NG license](https://github.com/espeak-ng/espeak-ng).

The agent looks in `models\kokoro-v1.0.onnx` and `models\voices-v1.0.bin`. Override either path with `VOLVOX_KOKORO_MODEL` or `VOLVOX_KOKORO_VOICES` if you store assets elsewhere.

Install Ollama for Windows, start it, and fetch the configured model:

```powershell
ollama pull llama3.2:3b
ollama list
```

Ollama must be listening locally on port 11434. No hosted service or Docker is used.

## Run and smoke test

```powershell
python .\bot.py
python .\bot.py --prompt "What services does Volvox Solutions offer?"
python .\bot.py --smoke-test
python .\bot.py --tts on --smoke-test --output-wav .\artifacts\response.wav
python .\test_tts.py
python .\play_wav.py .\artifacts\response.wav
```

The text smoke test sends a real prompt through Pipecat and exits nonzero if no generated text arrives. To exercise the full text-to-speech path, pass `--tts on`; it produces a WAV file after the Pipecat Kokoro processor receives the model response. `test_tts.py` independently synthesizes a short sentence and checks that the WAV is readable and non-silent. `play_wav.py` separately tests Windows speaker playback with the default audio device. Playback errors do not invalidate a successfully generated WAV.

In text mode, TTS is off by default. Run `python .\bot.py --mode text --tts on` to save a WAV without playing it. Use `--voice af_sarah` to choose another voice from the included voice pack and `--output-wav PATH` to change the output destination. A missing model or voice file, invalid voice, synthesis error, and WAV write error are reported clearly. Text mode does not open a microphone or play audio.

## Local speech recognition and microphone

The first STT run downloads the English `base.en` CTranslate2 model from [Systran/faster-whisper-base.en](https://huggingface.co/Systran/faster-whisper-base.en) into `models\whisper`. The repository currently reports about **148 MB** and MIT licensing. The model download needs internet once; transcription after that uses local CPU inference with `int8` compute. PyAV decodes WAV input; FFmpeg does not need a separate system installation.

Check input devices, then open the microphone briefly without writing audio:

```powershell
python .\test_stt.py --list-devices
python .\test_stt.py --mic-check
```

To record a real phrase and transcribe it, run the standalone test, speak after it starts, and press Enter to stop:

```powershell
python .\test_stt.py --record
```

For microphone-independent diagnostics, transcribe an existing WAV instead:

```powershell
python .\test_stt.py --wav .\artifacts\kokoro-preflight.wav --expect "speech test"
```

If no device appears, connect/enable a microphone. If it appears but cannot open, check Windows **Settings > Privacy & security > Microphone**, enable microphone access and desktop-app access, unmute the device, and close apps holding the input stream. The recording uses mono input at that device's default rate (the device metadata is printed); Whisper handles resampling during decoding. Silent or empty audio is rejected before transcription.

## Speech demo

For a fully automated speech-path check using a prerecorded WAV, without opening the microphone:

```powershell
python .\bot.py --mode audio-file --audio-file .\artifacts\kokoro-preflight.wav --output-wav .\artifacts\speech-e2e.wav
python .\play_wav.py .\artifacts\speech-e2e.wav
```

For the live push-to-talk conversation, use a console such as VS Code's PowerShell terminal:

```powershell
python .\bot.py --mode push-to-talk
```

At each prompt, press Enter to begin, speak, then press Enter again to stop and submit that utterance. The agent prints the recognized words, responds with Llama 3.2, synthesizes the answer, and plays it through the default Windows output device. Enter `q` at the between-turn prompt to exit. It preserves up to eight user/assistant turns in context. Use `--max-turns 2` for a bounded demo, `--mic-device 7` to select an enumerated input, `--tts off` for text replies, or `--playback off` to save WAVs without speaker output. Push-to-talk does not listen continuously and has no interruption handling.

Text mode stays unchanged: `python .\bot.py --mode text --prompt "..."`. Add `--tts on` to save a spoken WAV while keeping playback separate.

### Realtime VAD mode (Stage 1)

Pipecat 1.12.0 bundles `SileroVADAnalyzer` and its ONNX model, so the realtime mode adds no VAD dependency or separate model download. Its verified API accepts 8 or 16 kHz audio; this mode captures mono 16 kHz blocks, detects speech start/end, and submits a complete segment to local Whisper. It requires `sounddevice` and the existing `faster-whisper` install in `.venv312`.

Run:

```powershell
python .\test_vad.py --wav .\artifacts\kokoro-preflight.wav
python .\bot.py --mode realtime
```

The VAD smoke test needs an audio file containing speech and also verifies that a silence-only control stays quiet. In realtime mode, the microphone stream stays open between turns. Input is ignored while Ollama generates and Kokoro plays its answer; this prevents speaker audio from starting another turn, but it also means the current stage cannot handle interruptions. Speech is collected again when the response completes. Default thresholds require at least 0.45 seconds of segment audio, 0.004 normalized RMS, and 1.2 seconds of VAD silence before submission. Tune the silence and energy gates with `--vad-silence` and `--vad-min-rms` if needed. Ctrl+C closes the stream.

The automated VAD test does not verify your microphone. Use `python .\test_stt.py --mic-check` to check permission and signal level, then try `python .\bot.py --mode realtime` and speak a short sentence. The current development machine opened the default mic at 16 kHz, but its capture measured only 0.000183 peak, below the speech gate; a real spoken phrase has not been verified here. If `Speech detected.` never appears, check Windows microphone privacy, device selection (`--mic-device N`), mute state, and input gain. Existing `text`, `audio-file`, and `push-to-talk` modes remain available.

The Kokoro service implementation in this installed Pipecat version exposes streamed audio frames through its `create_stream` path. Realtime playback without a WAV round trip, interruption handling, acoustic echo control, and per-turn latency instrumentation are later stages and are not implemented or verified yet. Continue with those only after realtime microphone capture passes a spoken phrase test on the target laptop.

## Python and dependency compatibility

| Component | Current / considered version | Python 3.12 assessment |
| --- | --- | --- |
| Pipecat | `pipecat-ai==1.12.0` | Compatible: installed distribution metadata says `Requires-Python >=3.11`; 3.12 is within range. |
| Kokoro ONNX | `kokoro-onnx==0.5.0` | Installed in `.venv312`; its Windows dependencies installed successfully under Python 3.12.10. The release requires Python `>=3.10,<3.14`; Pipecat 1.12.0 declares `kokoro-onnx>=0.5.0,<1` in its Kokoro extra. |
| Local Whisper | `faster-whisper==1.2.1` | Installed in `.venv312`; package metadata requires Python 3.9+. Its CTranslate2 4.8.2 CPU extension loaded and reports `int8` support. PyAV 16.0.0 is pinned for Windows; faster-whisper imported and transcribed a WAV successfully. |
| Microphone capture | `sounddevice==0.5.6` | Installed in `.venv312`; Windows x86-64 wheel. PortAudio enumerated Windows input devices. A one-second input stream opened at 16 kHz mono, but measured only 0.000183 peak; a real spoken microphone recording still needs manual verification. |

The text-only `.venv` uses Python 3.14.7, but Kokoro ONNX 0.5.0 excludes Python 3.14. Python 3.12 is used for the combined local speech environment. The `base.en` model runs as CPU `int8` and downloads on first use; preload it while connected if runtime operation must remain offline.

Pipecat 1.12.0 has a `WhisperSTTService` backed by faster-whisper. This push-to-talk mode uses a small batch adapter: it records/transcribes a WAV before passing its text to the existing Pipecat LLM pipeline. This avoids requiring a live audio transport for the first local push-to-talk stage. The installed Pipecat service source and the current `PipelineWorker`/`WorkerRunner` APIs were inspected; no deprecated runner/task APIs were added.

Package metadata references: [Pipecat 1.12.0](https://pypi.org/project/pipecat-ai/1.12.0/), [Kokoro ONNX 0.5.0](https://pypi.org/project/kokoro-onnx/0.5.0/), [faster-whisper 1.2.1](https://pypi.org/project/faster-whisper/1.2.1/), [sounddevice 0.5.6](https://pypi.org/project/sounddevice/0.5.6/), and [PyAV 16.0.0 Windows wheels](https://pypi.org/project/av/16.0.0/).

## Recommended speech integration steps

1. Run `test_stt.py --mic-check` and `--record` in a normal VS Code PowerShell terminal, speak a short phrase, and verify the transcript.
2. Run `bot.py --mode push-to-talk` for multiple spoken turns; adjust Windows input level or select a device if transcripts are empty.
3. Keep model caches available offline after initial downloads; no continuous listening or interruption handling is implemented.

## Verification record

Verified: `.venv312` is Python 3.12.10 with Pipecat 1.12.0, Kokoro ONNX 0.5.0, faster-whisper 1.2.1, PyAV 16.0.0, and sounddevice 0.5.6. CTranslate2 CPU `int8` is available. `.venv` was not modified.

Verification run on 2026-10-09: `py_compile` passed for the agent and smoke-test modules; `pip check` passed in both environments. Text smoke tests passed in `.venv` (Python 3.14.7) and `.venv312` (Python 3.12.10). The two-turn Ollama/Pipecat context smoke passed. Standalone Kokoro generation passed and validated a 24 kHz non-silent WAV. `base.en` transcribed the prerecorded Kokoro WAV (recognized “Kakoro” for “Kokoro”); the integrated `bot.py --mode audio-file` run completed Whisper → Ollama through Pipecat → Kokoro and generated a non-silent response WAV. `test_stt.py --list-devices` found 15 inputs; the default Realtek array reports two input channels at 44.1 kHz. An elevated 0.5-second microphone stream opened and captured at 44.1 kHz mono, but the input was silent (peak 0.0), so no live spoken phrase or live microphone transcription has been verified. A generated response WAV completed the Windows speaker playback call; listening quality still needs human confirmation. The silent-WAV rejection path was also verified. The first PyAV 19.0.1 import was blocked by Application Control; PyAV 16.0.0 resolved it and is pinned. Microphone streaming and Kokoro temporary eSpeak DLL cleanup needed elevated execution in this environment.

Realtime Stage 1 verification (2026-10-09): installed Silero VAD passed `test_vad.py` on a speech WAV and an all-silence control, and the default Windows input stream opened at 16 kHz mono. Its measured peak was 0.000183, below the configured speech gate; no spoken live microphone test or realtime end-to-end turn has passed. Stage 1 is implemented but awaits a real microphone phrase test. Stages 2–4 were intentionally left unimplemented because of that hardware signal limitation.
