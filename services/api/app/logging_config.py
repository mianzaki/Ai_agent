import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "organization_id", "agent_id", "session_id", "path", "status_code", "transcription_ms", "llm_ms", "tts_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    voice_log_path = os.environ.get("VOLVOX_VOICE_LOG_PATH")
    if voice_log_path:
        path = Path(voice_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        voice_handler = logging.FileHandler(path, encoding="utf-8")
        voice_handler.setFormatter(JsonFormatter())
        voice_logger = logging.getLogger("volvox.voice")
        voice_logger.handlers.clear()
        voice_logger.addHandler(voice_handler)
