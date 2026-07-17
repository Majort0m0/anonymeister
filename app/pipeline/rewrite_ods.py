import io
from typing import Callable

import odf.opendocument
import odf.table
import odf.teletype
import odf.text


def _rewrite_cell(cell, transform: Callable[[str], str]) -> None:
    """Replace a single table cell's text content with transform(text),
    leaving cells with no text untouched.

    odf.teletype.extractText() flattens a cell's paragraph(s) (and any
    text:s/tab/line-break runs within them) into one plain string; there is
    no reliable separator preserved between multiple <text:p> siblings in a
    cell, so writing the transformed text back as a single fresh paragraph
    loses no information a reader of this cell could see anyway. All other
    cell attributes (style-name, formulas, number-columns-repeated,
    value-type, etc.) are left untouched since we only ever touch
    childNodes.
    """
    text = odf.teletype.extractText(cell)
    if not text:
        return

    new_text = transform(text)

    for child in list(cell.childNodes):
        cell.removeChild(child)

    paragraph = odf.text.P()
    odf.teletype.addTextToElement(paragraph, new_text)
    cell.addElement(paragraph)


def rewrite_ods(original_bytes: bytes, transform: Callable[[str], str]) -> bytes:
    """Return new .ods file bytes with every non-empty table cell's text
    replaced by transform(text), preserving sheets, rows, columns, and every
    cell attribute the library doesn't require us to touch.
    """
    try:
        document = odf.opendocument.load(io.BytesIO(original_bytes))
    except Exception as exc:
        raise ValueError(f"could not be opened as an ODF file: {exc}") from exc

    tables = document.getElementsByType(odf.table.Table)
    if not tables:
        raise ValueError(
            "this document has no spreadsheet tables to rewrite: it contains "
            "zero ODF table elements."
        )

    for sheet in tables:
        for cell in sheet.getElementsByType(odf.table.TableCell):
            _rewrite_cell(cell, transform)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
