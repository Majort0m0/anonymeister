import json
from typing import Callable


def _rewrite_value(value, transform: Callable[[str], str]):
    if isinstance(value, dict):
        return {key: _rewrite_value(val, transform) for key, val in value.items()}

    if isinstance(value, list):
        return [_rewrite_value(item, transform) for item in value]

    if isinstance(value, str):
        return transform(value)

    return value


def rewrite_json(original_bytes: bytes, transform: Callable[[str], str]) -> bytes:
    try:
        raw_text = original_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw_text = original_bytes.decode("latin-1")

    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"could not parse JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})."
        ) from exc

    rewritten = _rewrite_value(value, transform)

    return json.dumps(rewritten, indent=2, ensure_ascii=False, sort_keys=False).encode(
        "utf-8"
    )
