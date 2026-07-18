"""Thin wrapper around the local Ollama daemon.

All local-LLM calls in this app go through generate() so there is a single
place that turns a broken connection to the daemon, or a model that hasn't
been pulled yet, into an actionable error message instead of a raw
traceback bubbling up to the UI.
"""

from __future__ import annotations

import ollama

from app.config import OLLAMA_HOST, OLLAMA_NUM_CTX
from app.settings import get_ollama_model


def generate(prompt: str, system: str | None = None, temperature: float | None = None) -> str:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    model = get_ollama_model()
    options: dict[str, float] = {"num_ctx": OLLAMA_NUM_CTX}
    if temperature is not None:
        # Extraction/classification calls (deep_check) want low-variance,
        # systematic output rather than the model's default creative
        # sampling (Modelfile default is temperature=1) — omitted here means
        # "use the model's own default", so callers doing free-form
        # generation (summarize) are unaffected unless they opt in too.
        options["temperature"] = temperature

    try:
        client = ollama.Client(host=OLLAMA_HOST)
        response = client.chat(model=model, messages=messages, options=options)
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach the local Ollama model '{model}' at {OLLAMA_HOST}. "
            "Make sure the Ollama app/daemon is running and that the model has been "
            f'pulled (e.g. "ollama pull {model}").'
        ) from exc

    message = response["message"] if isinstance(response, dict) else response.message
    content = message["content"] if isinstance(message, dict) else message.content
    return content
