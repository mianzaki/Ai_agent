"""Process-local Kokoro ONNX synthesis with bounded, serialized inference."""

import io
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("volvox.tts")
MAX_TEXT_LENGTH = 5000
MAX_WAV_BYTES = 20 * 1024 * 1024
SUPPORTED_LANGUAGES = {"en-us", "en-gb", "es", "fr-fr", "hi", "it", "ja", "pt-br", "zh"}
VOICE_LANGUAGES = {
    **{voice: "en-us" for voice in ["af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx", "am_puck", "am_santa"]},
    **{voice: "en-gb" for voice in ["bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis"]},
    "ef_dora": "es", "em_alex": "es", "em_santa": "es", "ff_siwis": "fr-fr",
    "hf_alpha": "hi", "hf_beta": "hi", "hm_omega": "hi", "hm_psi": "hi",
    "if_sara": "it", "im_nicola": "it", "jf_alpha": "ja", "jf_gongitsune": "ja",
    "jf_nezumi": "ja", "jf_tebukuro": "ja", "jm_kumo": "ja", "pf_dora": "pt-br",
    "pm_alex": "pt-br", "pm_santa": "pt-br", "zf_xiaobei": "zh", "zf_xiaoni": "zh",
    "zf_xiaoxiao": "zh", "zf_xiaoyi": "zh", "zm_yunjian": "zh", "zm_yunxi": "zh",
    "zm_yunxia": "zh", "zm_yunyang": "zh",
}


class KokoroService:
    def __init__(self, model_path: Path, voices_path: Path) -> None:
        self._model_path = model_path
        self._voices_path = voices_path
        self._model: object | None = None
        self._voices: list[str] = []
        self._lock = threading.Lock()
        self._espeak_library_handle: Any = None
        self._dll_directory_handle: Any = None

    def load(self) -> None:
        if self._model is not None:
            return
        if not self._model_path.is_file() or not self._voices_path.is_file():
            logger.warning("kokoro_assets_missing")
            return
        try:
            api_dir = Path(__file__).resolve().parents[1]
            repo_root = api_dir.parents[1]
            for candidate in (repo_root / ".venv312" / "Lib" / "site-packages", repo_root / ".venv" / "Lib" / "site-packages"):
                if (candidate / "kokoro_onnx").is_dir():
                    import site
                    site.addsitedir(str(candidate))
                    break
            import importlib

            importlib.import_module("numpy")
            importlib.import_module("soundfile")
            self._configure_stable_espeak()
            Kokoro = importlib.import_module("kokoro_onnx").Kokoro

            self._model = Kokoro(str(self._model_path), str(self._voices_path))
            self._voices = sorted(self._model.get_voices())  # type: ignore[union-attr]
            logger.info("kokoro_model_loaded", extra={"voice_count": len(self._voices)})
        except Exception:
            logger.exception("kokoro_model_load_failed")
            self._model = None

    def _configure_stable_espeak(self) -> None:
        """Use the trusted bundled eSpeak DLL in place, avoiding phonemizer's temp copy.

        phonemizer-fork clones the library for each EspeakAPI to isolate its globals. Volvox
        already serializes inference and only creates one tokenizer per worker, so a single
        stable process-local DLL handle is safe for this workload.
        """
        import ctypes
        import importlib
        import sys

        api_module = importlib.import_module("phonemizer.backend.espeak.api")
        wrapper_module = importlib.import_module("phonemizer.backend.espeak.wrapper")
        original_api: Any = api_module.EspeakAPI
        library = Path(__import__("espeakng_loader").get_library_path()).resolve()
        data_path = Path(__import__("espeakng_loader").get_data_path()).resolve()
        if not library.is_file() or not data_path.is_dir():
            raise RuntimeError("The bundled eSpeak library or voice data is missing.")
        if sys.platform == "win32":
            self._dll_directory_handle = os.add_dll_directory(str(library.parent))
        self._espeak_library_handle = ctypes.CDLL(str(library))
        library_handle = self._espeak_library_handle

        initialization_lock = threading.Lock()
        initialized = False

        def stable_init(self: Any, _library: str | Path, configured_data_path: str | Path | None) -> None:
            nonlocal initialized
            self._library = library_handle
            with initialization_lock:
                if not initialized:
                    encoded_data = str(configured_data_path or data_path).encode("utf-8")
                    result = self._library.espeak_Initialize(0x02, 0, encoded_data, 0)
                    if result <= 0:
                        raise RuntimeError("eSpeak initialization failed.")
                    initialized = True
            self._library_path = library

        original_api.__init__ = stable_init
        wrapper_module.EspeakWrapper.set_library(str(library))
        wrapper_module.EspeakWrapper.set_data_path(str(data_path))

    @property
    def voices(self) -> list[str]:
        self.load()
        return self._voices.copy()

    def synthesize(self, text: str, voice: str, language: str, speed: float) -> tuple[bytes, int]:
        if not text.strip():
            raise ValueError("Enter some text to generate speech.")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"Text must be {MAX_TEXT_LENGTH:,} characters or fewer.")
        self.load()
        if self._model is None:
            raise RuntimeError("Speech generation is unavailable because the local voice model is not ready.")
        if voice not in self._voices:
            raise ValueError("Choose a voice available in the installed Kokoro voice pack.")
        if language not in SUPPORTED_LANGUAGES or VOICE_LANGUAGES.get(voice) != language:
            raise ValueError("That language is not supported by the selected voice.")
        if not 0.5 <= speed <= 2.0:
            raise ValueError("Speech speed must be between 0.5× and 2.0×.")
        with self._lock:
            import importlib
            np = importlib.import_module("numpy")
            sf = importlib.import_module("soundfile")

            samples, sample_rate = self._model.create(  # type: ignore[attr-defined]
                text, voice=voice, speed=speed, lang=language
            )
        audio = np.asarray(samples, dtype=np.float32)
        if audio.size == 0 or not np.isfinite(audio).all():
            raise RuntimeError("Speech generation did not return playable audio.")
        out = io.BytesIO()
        sf.write(out, audio, sample_rate, subtype="PCM_16", format="WAV")
        result = out.getvalue()
        if len(result) > MAX_WAV_BYTES:
            raise ValueError("Generated audio is too large. Try a shorter text.")
        return result, int(sample_rate)


def make_service() -> KokoroService:
    root = Path(__file__).resolve().parents[3]
    model = Path(os.environ.get("VOLVOX_KOKORO_MODEL", str(root / "models" / "kokoro-v1.0.onnx")))
    voices = Path(os.environ.get("VOLVOX_KOKORO_VOICES", str(root / "models" / "voices-v1.0.bin")))
    return KokoroService(model, voices)
