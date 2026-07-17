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

from app.config import OLLAMA_HOST, SPACY_MODELS
from app.schemas import DependencyStatus
from app.settings import get_ollama_model, get_whisper_model_size

_OLLAMA_HTTP_TIMEOUT = 2
_OLLAMA_PULL_TIMEOUT = 600
_SPACY_DOWNLOAD_TIMEOUT = 600


def _ollama_tags() -> list[str] | None:
    """List model names Ollama reports via its HTTP API, or None if
    unreachable. Deliberately HTTP-based rather than shelling out to the
    "ollama" CLI: OLLAMA_HOST may point at a remote/sibling-container Ollama
    (see Dockerfile/docker-compose.yml) that has no local CLI binary at all,
    and this must work identically for that case and for the native desktop
    app talking to a local Ollama."""
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_HOST}/api/tags", timeout=_OLLAMA_HTTP_TIMEOUT
        ) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None
    return [model.get("name", "") for model in payload.get("models", [])]


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


def _ollama_pull_via_http(model: str) -> bool:
    """Trigger a model pull through Ollama's HTTP API (POST /api/pull,
    streaming NDJSON progress) instead of the "ollama" CLI — see
    _ollama_tags() for why the CLI can't be relied on here."""
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/pull",
        data=json.dumps({"name": model}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_OLLAMA_PULL_TIMEOUT) as response:
            for _ in response:
                pass  # drain streamed progress lines; we only care that it completes
        return True
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


def attempt_auto_install(name: str) -> DependencyStatus:
    if name == f"ollama model {get_ollama_model()}":
        _ollama_pull_via_http(get_ollama_model())
        return _check_ollama_model()

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
