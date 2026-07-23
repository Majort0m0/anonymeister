"""Checks the local components the pipeline depends on (Ollama, spaCy
models) and reports what is missing with actionable instructions, per the
requirement that the app never leaves the user guessing why a local model is
unavailable.

Audio transcription needs no such check: faster-whisper decodes audio via
PyAV, which bundles its own FFmpeg libraries statically — there is no system
`ffmpeg` binary dependency to verify (confirmed by decoding a file with PATH
cleared entirely). An earlier version of this module checked for `ffmpeg` on
PATH anyway, which was actively misleading: it could fail even after
`brew install ffmpeg` because a macOS `.app` launched from Finder doesn't
inherit Homebrew's PATH additions from the user's shell profile, and "fixing"
it wouldn't have changed whether transcription actually worked either way.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Callable

from app.config import OLLAMA_HOST, SPACY_MODELS
from app.schemas import DependencyStatus
from app.settings import get_ollama_model, get_whisper_model_size

_OLLAMA_HTTP_TIMEOUT = 2
_OLLAMA_PULL_TIMEOUT = 600
_SPACY_DOWNLOAD_TIMEOUT = 600


def _ollama_tags_payload() -> list[dict] | None:
    """Raw `models` list from Ollama's /api/tags, or None if unreachable —
    shared by _ollama_tags() (names only, for the single-configured-model
    check) and list_ollama_models() (full inventory, for the Systemstatus
    display) so the request + error handling exists in exactly one place.
    Deliberately HTTP-based rather than shelling out to the "ollama" CLI:
    OLLAMA_HOST may point at a remote/sibling-container Ollama (see
    Dockerfile/docker-compose.yml) that has no local CLI binary at all, and
    this must work identically for that case and for the native desktop app
    talking to a local Ollama."""
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_HOST}/api/tags", timeout=_OLLAMA_HTTP_TIMEOUT
        ) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None
    return payload.get("models", [])


def _ollama_tags() -> list[str] | None:
    """List model names Ollama reports via its HTTP API, or None if
    unreachable."""
    models = _ollama_tags_payload()
    if models is None:
        return None
    return [model.get("name", "") for model in models]


def _format_bytes(n: float) -> str:
    """Human-readable byte size for pull-progress lines and the local-model
    list, e.g. "2.3 GB" — decimal (1000-based) units, matching Ollama's own
    CLI/API convention (`ollama list` reports sizes the same way), not the
    binary (1024-based) convention a naive KB/MB/GB implementation would
    default to. Using binary division here would silently disagree with
    what `ollama list` shows for the exact same model (e.g. a real 7.16 GB
    model would show as "6.7 GB" instead of "7.2 GB") — confirmed against
    this app's own installed Ollama."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} TB"


def _progress_bar(percent: float, width: int = 20) -> str:
    """Block-character progress bar matching the shape `ollama pull` itself
    draws in a real terminal (e.g. "▕████████░░░░░░░░░░▏") — used in the
    pull-progress lines below so the in-app display reads as authentically
    terminal-like as the text format allows, not just a bare percentage."""
    filled = max(0, min(width, round(width * percent / 100)))
    return "▕" + "█" * filled + "░" * (width - filled) + "▏"


def list_ollama_models() -> list[dict]:
    """Full local model inventory (name + human-readable size), for the
    Systemstatus panel's "locally available models" display. Unlike
    _ollama_tags() above (which only this module needs, to check ONE
    specific configured model by name), this exposes the complete picture
    the frontend shows the user. Returns an empty list if Ollama isn't
    reachable — matching how the rest of this app treats Ollama as an
    always-optional dependency, not surfacing an error for what's a
    routine, expected state (no Ollama installed/running yet)."""
    models = _ollama_tags_payload()
    if models is None:
        return []
    return [
        {"name": model["name"], "size": _format_bytes(model.get("size", 0))}
        for model in models
        if model.get("name")
    ]


def _check_ollama() -> DependencyStatus:
    if _ollama_tags() is not None:
        return DependencyStatus(
            name="ollama",
            available=True,
            detail=f"Ollama is reachable at {OLLAMA_HOST}.",
        )
    if shutil.which("ollama") is None:
        return DependencyStatus(
            name="ollama",
            available=False,
            detail=f"Ollama is not reachable at {OLLAMA_HOST}.",
            install_hint="https://ollama.com/download",
        )
    # The CLI exists locally but the HTTP API didn't respond — likely just
    # not started yet (this distinction is meaningless when OLLAMA_HOST
    # points elsewhere, e.g. Docker, but is a genuinely more useful message
    # for the native desktop app where "ollama" being on PATH implies it's
    # meant to be local).
    hint = "open -a Ollama" if platform.system() == "Darwin" else "ollama serve"
    return DependencyStatus(
        name="ollama",
        available=False,
        detail=f"Ollama is installed but not running (no response from {OLLAMA_HOST}).",
        install_hint=hint,
    )


def _check_ollama_model() -> DependencyStatus:
    model = get_ollama_model()
    name = f"ollama model {model}"
    tags = _ollama_tags()
    if tags is None:
        return DependencyStatus(
            name=name,
            available=False,
            detail=f"Could not reach Ollama at {OLLAMA_HOST} to check installed models.",
            install_hint=f"ollama pull {model}",
        )
    if model in tags:
        return DependencyStatus(
            name=name,
            available=True,
            detail=f"Model '{model}' is available on the Ollama server.",
        )
    return DependencyStatus(
        name=name,
        available=False,
        detail=f"Model '{model}' was not found on the Ollama server ({OLLAMA_HOST}).",
        install_hint=f"ollama pull {model}",
    )


def _ollama_pull_via_http(
    model: str,
    on_pull_progress: Callable[[list[str], float | None], None] | None = None,
) -> bool:
    """Trigger a model pull through Ollama's HTTP API (POST /api/pull,
    streaming NDJSON progress) instead of the "ollama" CLI — see
    _ollama_tags() for why the CLI can't be relied on here.

    Ollama streams one JSON object per line as the pull advances: first
    {"status": "pulling manifest"}, then many {"status": "pulling <digest>",
    "digest": "sha256:...", "total": N, "completed": M} lines per layer as
    it downloads (one per network read, not one per percent — a large layer
    can produce thousands of these), then {"status": "verifying sha256
    digest"}, {"status": "writing manifest"}, {"status": "success"} — this
    last line is the only real success signal. A connection that drops
    mid-download closes the HTTP response cleanly from Python's perspective
    (chunked-transfer decoding treats an unexpected close as plain EOF, not
    an error — confirmed directly against this function), so `for raw_line
    in response:` just ends the loop with no exception at all if that
    happens; without explicitly checking for the "success" status, this
    function would return True for a pull that never actually finished.

    `on_pull_progress`, if given, is called after every parsed line with the
    FULL current ordered list of human-readable terminal-style text lines
    plus the overall percent computed from real byte counts across every
    layer seen so far — a full snapshot each time, not a diff, matching how
    this app's GET /api/progress/{job_id} already returns a full snapshot
    per poll rather than incremental updates (the log stays small, at most
    a few dozen lines, so re-sending it whole is simpler and more robust
    than diffing). Per-layer lines are updated IN PLACE (keyed by digest)
    rather than appended on every tick — a real terminal overwrites the
    line too; appending every tick would flood the log with near-duplicate
    lines for a large layer.
    """
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/pull",
        data=json.dumps({"name": model}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    lines: list[str] = []
    line_index: dict[str, int] = {}
    layer_progress: dict[str, tuple[int, int]] = {}  # digest -> (completed, total)

    def _set_line(key: str, text: str) -> None:
        if key in line_index:
            lines[line_index[key]] = text
        else:
            line_index[key] = len(lines)
            lines.append(text)

    def _overall_percent() -> float | None:
        if not layer_progress:
            return None
        completed = sum(c for c, _ in layer_progress.values())
        total = sum(t for _, t in layer_progress.values())
        if total <= 0:
            return None
        # Clamped like _recompute_progress()'s equivalent elsewhere in the
        # job-progress system — Ollama can report a completed byte count
        # that transiently exceeds total for a layer near the end of its
        # download, which would otherwise surface as e.g. "103.4%".
        return round(min(100.0, completed / total * 100), 1)

    saw_success = False
    try:
        with urllib.request.urlopen(request, timeout=_OLLAMA_PULL_TIMEOUT) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                try:
                    event = json.loads(raw_line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # A truncated line (e.g. a network hiccup cutting a line
                    # off mid multi-byte character) decodes as garbage, not
                    # as an error condition worth failing the whole pull
                    # over — skip it and keep reading, same as a plain
                    # malformed JSON line.
                    continue

                status = event.get("status", "")
                digest = event.get("digest")
                if digest:
                    total = event.get("total", 0)
                    completed = event.get("completed", 0)
                    layer_progress[digest] = (completed, total)
                    short_digest = digest.removeprefix("sha256:")[:12]
                    if total > 0:
                        percent = min(100.0, completed / total * 100)
                        text = (
                            f"pulling {short_digest}: {_progress_bar(percent)} {percent:5.1f}% "
                            f"({_format_bytes(completed)}/{_format_bytes(total)})"
                        )
                    else:
                        text = f"pulling {short_digest}: {status}"
                    _set_line(digest, text)
                elif status:
                    _set_line(status, status)
                    if status == "success":
                        saw_success = True

                if on_pull_progress:
                    on_pull_progress(list(lines), _overall_percent())
        return saw_success
    except (urllib.error.URLError, OSError):
        return False


def _check_spacy_models() -> list[DependencyStatus]:
    try:
        import spacy.util
    except ImportError:
        return [
            DependencyStatus(
                name=f"spaCy model {model_name}",
                available=False,
                detail="spaCy is not installed.",
                install_hint="pip install spacy",
            )
            for model_name in SPACY_MODELS.values()
        ]

    statuses = []
    for model_name in SPACY_MODELS.values():
        name = f"spaCy model {model_name}"
        if spacy.util.is_package(model_name):
            statuses.append(
                DependencyStatus(
                    name=name,
                    available=True,
                    detail=f"spaCy model '{model_name}' is installed.",
                )
            )
        else:
            statuses.append(
                DependencyStatus(
                    name=name,
                    available=False,
                    detail=f"spaCy model '{model_name}' is not installed.",
                    install_hint=f"python -m spacy download {model_name}",
                )
            )
    return statuses


def _check_whisper_cache() -> DependencyStatus:
    size = get_whisper_model_size()
    return DependencyStatus(
        name="faster-whisper model cache",
        available=True,
        detail=(
            f"faster-whisper downloads the '{size}' model automatically on "
            "first transcription and caches it locally afterwards; no "
            "manual setup is required."
        ),
    )


def check_dependencies() -> list[DependencyStatus]:
    statuses = [_check_ollama(), _check_ollama_model()]
    statuses.extend(_check_spacy_models())
    statuses.append(_check_whisper_cache())
    return statuses


def attempt_auto_install(
    name: str,
    on_pull_progress: Callable[[list[str], float | None], None] | None = None,
) -> DependencyStatus:
    if name == f"ollama model {get_ollama_model()}":
        pulled = _ollama_pull_via_http(get_ollama_model(), on_pull_progress=on_pull_progress)
        status = _check_ollama_model()
        if not pulled and not status.available:
            # The pull stream ended without ever reporting "success" (see
            # _ollama_pull_via_http()'s docstring — a dropped connection is
            # otherwise silent) and the model genuinely still isn't there —
            # give a specific reason instead of the generic "not found"
            # _check_ollama_model() would otherwise report, which would
            # look identical to never having tried at all.
            return DependencyStatus(
                name=status.name,
                available=False,
                detail="Der Download wurde unterbrochen, bevor er abgeschlossen war.",
                install_hint=status.install_hint,
            )
        return status

    if name.startswith("spaCy model "):
        model_name = name.removeprefix("spaCy model ")
        if model_name not in SPACY_MODELS.values():
            raise ValueError(f"Unrecognized dependency name: {name!r}")
        try:
            subprocess.run(
                [sys.executable, "-m", "spacy", "download", model_name],
                capture_output=True,
                text=True,
                timeout=_SPACY_DOWNLOAD_TIMEOUT,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return next(s for s in _check_spacy_models() if s.name == name)

    if name == "ollama":
        status = _check_ollama()
        if status.available:
            return status
        return DependencyStatus(
            name=status.name,
            available=False,
            detail=status.detail
            + " Ollama must be installed or started manually; automated "
            "system installs are not performed.",
            install_hint=status.install_hint,
        )

    if name == "faster-whisper model cache":
        return _check_whisper_cache()

    raise ValueError(f"Unrecognized dependency name: {name!r}")
