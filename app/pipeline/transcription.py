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
from typing import Callable

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


def transcribe_audio(
    path: Path,
    on_progress: Callable[[str, int, int], None] | None = None,
    on_plan: Callable[[list[tuple[str, int]]], None] | None = None,
) -> tuple[str, str]:
    """Transcribe an audio file and return (full_text, detected_language_code).

    The language code is whatever Whisper detected from the audio (e.g. "de",
    "en", or something else entirely) — it is returned as-is, uncoerced, for
    the caller to fall back on.

    Reports its own "transcribe" stage (one unit per second of audio) rather
    than sharing app.pipeline.pipeline.analyze_file()'s generic single-unit
    "ingest" stage — model.transcribe()'s `info.duration` is known immediately
    (computed from an initial pass), before the lazy `segments` generator is
    actually decoded, so the real audio length is available up front to plan
    against, and each yielded segment's own `.end` timestamp gives genuine
    incremental progress through that length as decoding proceeds. This also
    means app/progress_calibration.py learns a transcription-SPEED ratio
    (wall-clock seconds per second of audio) under a distinct calibration key
    — a ratio generalizes correctly to a next audio file of any length, unlike
    the old shared "ingest" estimate, which mixed near-instant text-document
    parsing (typically a couple of seconds, and the far more common case) with
    multi-minute audio transcriptions under one average: that average stayed
    text-biased-fast, so an audio job blew past it almost immediately, and the
    progress UI would sit stuck (ETA gone, percent pinned near 99%) for the
    entire real transcription.
    """
    model = _get_model()

    try:
        segments, info = model.transcribe(str(path))
        total_units = max(1, round(info.duration))
        if on_plan:
            on_plan([("transcribe", total_units)])
        if on_progress:
            on_progress("transcribe", 0, total_units)

        texts = []
        for segment in segments:
            texts.append(segment.text.strip())
            if on_progress:
                on_progress("transcribe", min(round(segment.end), total_units), total_units)
    except Exception as exc:
        raise RuntimeError(
            f"Could not decode audio file '{path.name}'. The file format may "
            "be unsupported or the file may be corrupted."
        ) from exc

    full_text = " ".join(text for text in texts if text)
    return full_text, info.language
