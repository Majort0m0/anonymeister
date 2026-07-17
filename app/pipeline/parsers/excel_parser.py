from pathlib import Path

import openpyxl
import xlrd


def _format_row(values) -> str:
    cells = [str(value) for value in values if value not in (None, "")]
    return " | ".join(cells)


def _read_xlsx(path: Path) -> str:
    try:
        workbook = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError(
            f"'{path.name}' could not be opened as an Excel file: {exc}"
        ) from exc

    sections = []
    for sheet in workbook.worksheets:
        lines = [f"## {sheet.title}"]
        for row in sheet.iter_rows(values_only=True):
            line = _format_row(row)
            if line:
                lines.append(line)
        if len(lines) > 1:
            sections.append("\n".join(lines))

    if not sections:
        raise ValueError(
            f"'{path.name}' contains no extractable content: the Excel file has no "
            "sheets, or every sheet is empty."
        )

    return "\n\n".join(sections)


def _read_xls(path: Path) -> str:
    try:
        workbook = xlrd.open_workbook(str(path))
    except Exception as exc:
        raise ValueError(
            f"'{path.name}' could not be opened as an Excel file: {exc}"
        ) from exc

    sections = []
    for sheet in workbook.sheets():
        lines = [f"## {sheet.name}"]
        for row_idx in range(sheet.nrows):
            line = _format_row(sheet.row_values(row_idx))
            if line:
                lines.append(line)
        if len(lines) > 1:
            sections.append("\n".join(lines))

    if not sections:
        raise ValueError(
            f"'{path.name}' contains no extractable content: the Excel file has no "
            "sheets, or every sheet is empty."
        )

    return "\n\n".join(sections)


def read_excel(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".xls":
        return _read_xls(path)

    if suffix in (".xlsx", ".xlsm", ".xltx", ".xltm"):
        return _read_xlsx(path)

    raise ValueError(
        f"'{path.name}' has an unsupported Excel suffix '{suffix}' for read_excel()."
    )
