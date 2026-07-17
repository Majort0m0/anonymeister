import json
from pathlib import Path


def read_json(path: Path) -> str:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw_text = path.read_text(encoding="latin-1")

    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"'{path.name}' is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})."
        ) from exc

    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False)
