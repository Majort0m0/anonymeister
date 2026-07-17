"""Small persisted user-settings store for choices made in the Systemstatus
UI's model pickers (Ollama chat model, faster-whisper size).

Each setting is layered under its app.config env-var fallback: an explicit
env var (e.g. OLLAMA_MODEL/WHISPER_MODEL_SIZE set by Docker) always wins over
the UI choice, since it is a deliberate deployment-level override, not a
locally-clicked preference. Otherwise the saved choice applies, falling back
to the hardcoded default if nothing was ever saved.
"""

from __future__ import annotations

import json
import os
import threading

from app.config import APP_DATA_DIR
from app.config import OLLAMA_MODEL as _DEFAULT_OLLAMA_MODEL
from app.config import WHISPER_MODEL_SIZE as _DEFAULT_WHISPER_MODEL_SIZE

_SETTINGS_PATH = APP_DATA_DIR / "settings.json"
_lock = threading.Lock()


def _read() -> dict:
    try:
        return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _get_setting(key: str, env_var: str, default: str) -> str:
    if env_var in os.environ:
        return default
    return _read().get(key) or default


def _set_setting(key: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Value must not be empty.")
    with _lock:
        data = _read()
        data[key] = value
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH.write_text(json.dumps(data), encoding="utf-8")
    return value


def get_ollama_model() -> str:
    return _get_setting("ollama_model", "OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)


def set_ollama_model(name: str) -> str:
    return _set_setting("ollama_model", name)


def get_whisper_model_size() -> str:
    return _get_setting("whisper_model_size", "WHISPER_MODEL_SIZE", _DEFAULT_WHISPER_MODEL_SIZE)


def set_whisper_model_size(size: str) -> str:
    return _set_setting("whisper_model_size", size)
