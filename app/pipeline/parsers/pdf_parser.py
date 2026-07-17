from pathlib import Path

import pdfplumber
from pypdf import PdfReader


def _read_with_pdfplumber(path: Path) -> str:
    with pdfplumber.open(str(path)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n\n".join(pages)


def _read_with_pypdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def read_pdf(path: Path) -> str:
    try:
        text = _read_with_pdfplumber(path)
    except Exception:
        text = ""

    if not text.strip():
        try:
            text = _read_with_pypdf(path)
        except Exception:
            text = ""

    if not text.strip():
        raise ValueError(
            f"'{path.name}' appears to be a scanned or image-based PDF with no "
            "extractable text layer. OCR is not supported; please provide a "
            "text-based PDF or convert it with an OCR tool first."
        )

    return text
