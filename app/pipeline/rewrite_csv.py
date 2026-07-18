import csv
import io
from typing import Callable


def rewrite_csv(original_bytes: bytes, transform: Callable[[str], str]) -> bytes:
    try:
        content = original_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = original_bytes.decode("latin-1")

    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel  # default "," delimiter

    rows = list(csv.reader(content.splitlines(), dialect=dialect))

    if not rows:
        raise ValueError("The CSV file is empty.")

    # Row 0 (assumed header) is left untouched — see rewrite_excel.py's
    # _rewrite_xlsx() for why: an isolated header word has no sentence
    # context for spaCy's NER to work with and can get misclassified as PII
    # (observed), scrambling column labels in the reusable copy for no
    # privacy benefit — a header describes the column, it isn't user data.
    transformed_rows = [rows[0]] + [[transform(cell) for cell in row] for row in rows[1:]]

    buffer = io.StringIO()
    writer = csv.writer(buffer, dialect=dialect)
    writer.writerows(transformed_rows)

    return buffer.getvalue().encode("utf-8")
