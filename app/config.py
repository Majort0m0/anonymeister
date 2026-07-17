import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _default_output_dir() -> Path:
    # A PyInstaller-frozen app's __file__ resolves to a path inside the
    # (signed, read-only-in-spirit) app bundle/install dir — writing there
    # breaks code signing and isn't guaranteed writable once installed
    # (e.g. /Applications). Running from source (this repo, unfrozen) keeps
    # the original BASE_DIR/output behavior.
    if not getattr(sys, "frozen", False):
        return BASE_DIR / "output"

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Anonymizer"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "Anonymizer"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "anonymizer"
    return base / "output"


# Overridable so a mounted volume (Docker) or a different install location can
# relocate where generated files land, without touching any other code.
OUTPUT_DIR = Path(os.environ.get("ANONYMIZER_OUTPUT_DIR", str(_default_output_dir())))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Ollama — OLLAMA_HOST must be overridable: inside a Docker container,
# "localhost" refers to the container itself, not the host machine (or a
# sibling "ollama" container), so the default only works for the native
# desktop app running directly on the host.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:12b")

# faster-whisper
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "small")  # tiny|base|small|medium|large-v3 - small fits 16GB comfortably
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")  # good speed/RAM tradeoff on Apple Silicon CPU

# Presidio / spaCy
SPACY_MODELS = {
    "de": "de_core_news_lg",
    "en": "en_core_web_lg",
}
DEFAULT_LANGUAGE = "de"
SUPPORTED_PHONE_REGIONS = ["DE", "AT", "CH", "US", "GB"]

# Presidio ships country-specific structured-ID recognizers (US SSN, UK NHS, ...)
# tagged with a lowercase ISO-3166-1-ish country_code. Locales outside this list
# are excluded so an unrelated country's ID pattern (e.g. a UK NHS checksum)
# can't coincidentally out-score and swallow a real match (e.g. a phone number)
# from a country we don't otherwise support.
RELEVANT_ID_COUNTRIES = ["de", "at", "ch", "us"]

# 127.0.0.1 is correct for the native desktop app (pywebview talks to its own
# local backend only); a Docker container needs 0.0.0.0 to accept connections
# from outside the container — set directly via the container's CMD/uvicorn
# invocation rather than this default, so the desktop app's behavior is
# unaffected. SERVER_HOST/PORT are still overridable here for any other
# deployment that needs it.
SERVER_HOST = os.environ.get("ANONYMIZER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("ANONYMIZER_PORT", "8765"))
