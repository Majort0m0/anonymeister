import csv
from pathlib import Path


def read_csv(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1")

    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel  # default "," delimiter

    rows = list(csv.reader(content.splitlines(), dialect=dialect))

    if not rows:
        raise ValueError(f"'{path.name}' is an empty CSV file.")

    return "\n".join(" | ".join(row) for row in rows)
