"""Audio transcription via faster-whisper.

The Whisper model is loaded lazily and cached at module scope: loading it is
expensive (seconds of disk/RAM work even at "small" size), so it must survive
across calls rather than being reloaded per file. The cache is keyed by size
so a mid-session change of the Systemstatus size picker (app/settings.py)
loads the newly picked size on the next transcription instead of silently
keeping the old one.
"""

from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel

from app.config import WHISPER_COMPUTE_TYPE
from app.settings import get_whisper_model_size

_model: WhisperModel | None = None
_model_size: str | None = None


def _get_model() -> WhisperModel:
    global _model, _model_size
    size = get_whisper_model_size()
    if _model is None or _model_size != size:
        _model = WhisperModel(
            size,
            device="cpu",
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        _model_size = size
    return _model


def transcribe_audio(path: Path) -> tuple[str, str]:
    """Transcribe an audio file and return (full_text, detected_language_code).

    The language code is whatever Whisper detected from the audio (e.g. "de",
    "en", or something else entirely) — it is returned as-is, uncoerced, for
    the caller to fall back on.
    """
    model = _get_model()

    try:
        segments, info = model.transcribe(str(path))
        texts = [segment.text.strip() for segment in segments]
    except Exception as exc:
        raise RuntimeError(
            f"Could not decode audio file '{path.name}'. The file format may "
            "be unsupported or the file may be corrupted."
        ) from exc

    full_text = " ".join(text for text in texts if text)
    return full_text, info.language
