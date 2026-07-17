"""File and clipboard ingest: extract raw text and detect its language.

Text extraction must happen before anonymization/summarization can run, so
this module has no dependency on the rest of the pipeline — it only produces
an IngestResult that later stages consume.
"""

from pathlib import Path

from langdetect import LangDetectException, detect

from app.config import DEFAULT_LANGUAGE
from app.schemas import IngestResult, SourceKind
from app.pipeline.parsers.clipboard import read_clipboard
from app.pipeline.parsers.csv_parser import read_csv
from app.pipeline.parsers.docx_parser import read_docx
from app.pipeline.parsers.excel_parser import read_excel
from app.pipeline.parsers.json_parser import read_json
from app.pipeline.parsers.odf_parser import read_odf
from app.pipeline.parsers.pdf_parser import read_pdf
from app.pipeline.parsers.txt_md import read_txt_or_md

TEXT_EXTENSIONS = {".txt", ".md"}
DOCX_EXTENSIONS = {".docx", ".doc"}
PDF_EXTENSIONS = {".pdf"}
EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}
CSV_EXTENSIONS = {".csv"}
JSON_EXTENSIONS = {".json"}
ODF_EXTENSIONS = {".odt", ".ods", ".odp"}
AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma",
    ".opus", ".aiff", ".aif", ".caf", ".webm",
}

SUPPORTED_EXTENSIONS = (
    TEXT_EXTENSIONS
    | DOCX_EXTENSIONS
    | PDF_EXTENSIONS
    | EXCEL_EXTENSIONS
    | CSV_EXTENSIONS
    | JSON_EXTENSIONS
    | ODF_EXTENSIONS
)

# Tabular/structured formats that can be re-exported as an anonymized copy in
# their original format, not just flattened into the markdown transcript.
# .odt/.odp (prose-like ODF documents) are deliberately excluded — only .ods
# has the row/column structure worth preserving.
STRUCTURED_REWRITE_EXTENSIONS = EXCEL_EXTENSIONS | CSV_EXTENSIONS | JSON_EXTENSIONS | {".ods"}


def _detect_language(text: str) -> str:
    try:
        code = detect(text)
    except LangDetectException:
        return DEFAULT_LANGUAGE

    if code in ("de", "en"):
        return code
    return DEFAULT_LANGUAGE


def ingest_file(path: Path) -> IngestResult:
    suffix = path.suffix.lower()

    if suffix in AUDIO_EXTENSIONS:
        raise ValueError(
            f"'{path.name}' is an audio file ({suffix}). Audio must be routed "
            "through the transcription module, not ingest_file()."
        )

    if suffix in TEXT_EXTENSIONS:
        raw_text = read_txt_or_md(path)
        source_kind = SourceKind.TEXT
    elif suffix in DOCX_EXTENSIONS:
        raw_text = read_docx(path)
        source_kind = SourceKind.DOCX
    elif suffix in PDF_EXTENSIONS:
        raw_text = read_pdf(path)
        source_kind = SourceKind.PDF
    elif suffix in EXCEL_EXTENSIONS:
        raw_text = read_excel(path)
        source_kind = SourceKind.EXCEL
    elif suffix in CSV_EXTENSIONS:
        raw_text = read_csv(path)
        source_kind = SourceKind.CSV
    elif suffix in JSON_EXTENSIONS:
        raw_text = read_json(path)
        source_kind = SourceKind.JSON
    elif suffix in ODF_EXTENSIONS:
        raw_text = read_odf(path)
        source_kind = SourceKind.ODF
    else:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported file type '{suffix}' for '{path.name}'. "
            f"Supported extensions are: {supported}."
        )

    return IngestResult(
        source_filename=path.name,
        source_kind=source_kind,
        raw_text=raw_text,
        detected_language=_detect_language(raw_text),
    )


def ingest_clipboard() -> IngestResult:
    raw_text = read_clipboard()
    return IngestResult(
        source_filename="clipboard",
        source_kind=SourceKind.TEXT,
        raw_text=raw_text,
        detected_language=_detect_language(raw_text),
    )
