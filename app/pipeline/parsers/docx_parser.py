from pathlib import Path

import docx


def read_docx(path: Path) -> str:
    if path.suffix.lower() == ".doc":
        raise ValueError(
            f"'{path.name}' is a legacy .doc file (old binary Word format), which "
            "python-docx cannot read. Please re-save it as .docx from Word, "
            "LibreOffice, or Pages first, then try again."
        )

    document = docx.Document(str(path))

    parts = [paragraph.text for paragraph in document.paragraphs]

    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))

    return "\n".join(parts)
