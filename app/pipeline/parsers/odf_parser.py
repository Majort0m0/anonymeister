from pathlib import Path

import odf.opendocument
import odf.table
import odf.teletype
from odf.namespaces import TEXTNS

_BLOCK_QNAMES = {(TEXTNS, "p"), (TEXTNS, "h")}


def _walk_blocks(node, lines: list[str]) -> None:
    """Recursively descend the document tree, collecting the text of each
    block-level element (paragraph/heading) as its own line.

    A plain odf.teletype.extractText(document.topnode) call flattens the
    whole tree into one run with no separators at all between paragraphs
    (and even picks up unrelated text like the generator string in
    <office:meta>), so we walk block elements ourselves and only delegate to
    extractText() for the leaf content of each one.
    """
    for child in getattr(node, "childNodes", []):
        if getattr(child, "qname", None) in _BLOCK_QNAMES:
            text = odf.teletype.extractText(child).strip()
            if text:
                lines.append(text)
        else:
            _walk_blocks(child, lines)


def _read_ods_tables(document) -> str:
    """Table-aware extraction for .ods: walks sheets/rows/cells directly so
    spreadsheet content keeps its row/column structure instead of collapsing
    into one flat run of cell text (which is all a whole-tree extractText()
    call would give us here).
    """
    sections = []
    for sheet in document.getElementsByType(odf.table.Table):
        name = sheet.getAttribute("name") or "Sheet"
        lines = [f"## {name}"]
        for row in sheet.getElementsByType(odf.table.TableRow):
            values = [
                odf.teletype.extractText(cell).strip()
                for cell in row.getElementsByType(odf.table.TableCell)
            ]
            line = " | ".join(value for value in values if value)
            if line:
                lines.append(line)
        if len(lines) > 1:
            sections.append("\n".join(lines))

    return "\n\n".join(sections)


def read_odf(path: Path) -> str:
    try:
        document = odf.opendocument.load(str(path))
    except Exception as exc:
        raise ValueError(
            f"'{path.name}' could not be opened as an ODF file: {exc}"
        ) from exc

    text = ""
    if path.suffix.lower() == ".ods":
        text = _read_ods_tables(document).strip()

    if not text:
        # Uniform fallback for .odt/.odp (and .ods if the table walk above
        # found nothing): recursively pull every paragraph/heading's text out
        # of the whole document tree, regardless of document type.
        lines: list[str] = []
        _walk_blocks(document.topnode, lines)
        text = "\n".join(lines).strip()

    if not text:
        raise ValueError(
            f"'{path.name}' contains no extractable content: the ODF file "
            "has no readable text."
        )

    return text
