"""Checks the local components the pipeline depends on (ffmpeg, Ollama, spaCy
models) and reports what is missing with actionable instructions, per the
requirement that the app never leaves the user guessing why a local model is
unavailable.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from app.config import OLLAMA_HOST, OLLAMA_MODEL, SPACY_MODELS
from app.schemas import DependencyStatus

_OLLAMA_HTTP_TIMEOUT = 2
_OLLAMA_PULL_TIMEOUT = 600
_SPACY_DOWNLOAD_TIMEOUT = 600


def _check_ffmpeg() -> DependencyStatus:
    if shutil.which("ffmpeg") is not None:
        return DependencyStatus(
            name="ffmpeg", available=True, detail="ffmpeg was found on PATH."
        )
    if platform.system() == "Windows":
        hint = "Install ffmpeg from https://ffmpeg.org/download.html and add it to your PATH."
    else:
        hint = "brew install ffmpeg"
    return DependencyStatus(
        name="ffmpeg",
        available=False,
        detail="ffmpeg was not found on PATH. It is required for audio transcription.",
        install_hint=hint,
    )


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
    name = f"ollama model {OLLAMA_MODEL}"
    tags = _ollama_tags()
    if tags is None:
        return DependencyStatus(
            name=name,
            available=False,
            detail=f"Could not reach Ollama at {OLLAMA_HOST} to check installed models.",
            install_hint=f"ollama pull {OLLAMA_MODEL}",
        )
    if OLLAMA_MODEL in tags:
        return DependencyStatus(
            name=name,
            available=True,
            detail=f"Model '{OLLAMA_MODEL}' is available on the Ollama server.",
        )
    return DependencyStatus(
        name=name,
        available=False,
        detail=f"Model '{OLLAMA_MODEL}' was not found on the Ollama server ({OLLAMA_HOST}).",
        install_hint=f"ollama pull {OLLAMA_MODEL}",
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
    return DependencyStatus(
        name="faster-whisper model cache",
        available=True,
        detail=(
            "faster-whisper downloads its model automatically on first "
            "transcription and caches it locally afterwards; no manual setup "
            "is required."
        ),
    )


def check_dependencies() -> list[DependencyStatus]:
    statuses = [_check_ffmpeg(), _check_ollama(), _check_ollama_model()]
    statuses.extend(_check_spacy_models())
    statuses.append(_check_whisper_cache())
    return statuses


def attempt_auto_install(name: str) -> DependencyStatus:
    if name == f"ollama model {OLLAMA_MODEL}":
        _ollama_pull_via_http(OLLAMA_MODEL)
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

    if name == "ffmpeg":
        status = _check_ffmpeg()
        if status.available:
            return status
        return DependencyStatus(
            name=status.name,
            available=False,
            detail=status.detail
            + " ffmpeg must be installed manually; automated system package "
            "installs are not performed.",
            install_hint=status.install_hint,
        )

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
