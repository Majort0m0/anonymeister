"""Audio transcription via faster-whisper.

The Whisper model is loaded lazily and cached at module scope: loading it is
expensive (seconds of disk/RAM work even at "small" size), so it must survive
across calls rather than being reloaded per file.
"""

from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel

from app.config import WHISPER_COMPUTE_TYPE, WHISPER_MODEL_SIZE

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device="cpu",
            compute_type=WHISPER_COMPUTE_TYPE,
        )
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
            f"Could not decode audio file '{path.name}'. This usually means "
            "ffmpeg is missing or the file format is unsupported. Make sure "
            "ffmpeg is installed and available on PATH, then try again."
        ) from exc

    full_text = " ".join(text for text in texts if text)
    return full_text, info.language
