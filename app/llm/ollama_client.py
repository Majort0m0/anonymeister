"""Thin wrapper around the local Ollama daemon.

All local-LLM calls in this app go through generate() so there is a single
place that turns a broken connection to the daemon, or a model that hasn't
been pulled yet, into an actionable error message instead of a raw
traceback bubbling up to the UI.
"""

from __future__ import annotations

import ollama

from app.config import OLLAMA_HOST, OLLAMA_MODEL


def generate(prompt: str, system: str | None = None) -> str:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        client = ollama.Client(host=OLLAMA_HOST)
        response = client.chat(model=OLLAMA_MODEL, messages=messages)
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach the local Ollama model '{OLLAMA_MODEL}' at {OLLAMA_HOST}. "
            "Make sure the Ollama app/daemon is running and that the model has been "
            f'pulled (e.g. "ollama pull {OLLAMA_MODEL}").'
        ) from exc

    message = response["message"] if isinstance(response, dict) else response.message
    content = message["content"] if isinstance(message, dict) else message.content
    return content
