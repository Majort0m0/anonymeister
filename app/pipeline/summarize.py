"""Summarization of text via the local Ollama model.

Normally given the final, fully-processed anonymized text (see
app.pipeline.pipeline's module docstring: this is a correctness requirement,
not a privacy precaution — a summary of an "anonymized" document has to
summarize the actually-anonymized text, or it would leak exactly what the
user asked to have redacted). The one deliberate exception is
`PipelineOptions.anonymize=False` (pipeline.py's
`_finalize_without_anonymization()`), where the user explicitly chose to
skip redaction entirely — there, this is called with the raw original text
instead, via `anonymized=False` below, which selects a prompt that doesn't
falsely claim placeholders are present.

`style` (SummaryStyle, schemas.py) is the second, independent axis: COMPACT
is the original, still-default style (a short paragraph + optional bullet
facts). DETAILED produces a "Kernaussagen"/key-takeaways bullet list up
front, followed by a longer, section-structured summary — for a user who
wants more than a paragraph out of a long document. Both styles get their
own anonymized/raw × DE/EN prompt pair (4 total each), so there are 8 prompt
constants below; `style` and `anonymized` are independent choices (any
combination is valid), which is why they're selected in two separate steps
rather than one flat lookup table.
"""

from __future__ import annotations

from app.llm.ollama_client import generate
from app.schemas import SummaryStyle

_SYSTEM_ANONYMIZED_COMPACT_DE = (
    "Du bist ein Assistent, der bereits anonymisierte Texte zusammenfasst. "
    "Der Eingabetext wurde bereits anonymisiert: eckige Platzhalter wie [PERSON], "
    "[EMAIL_ADDRESS] oder [ORGANIZATION] sind absichtliche Schwärzungen und stehen für "
    "entfernte personenbezogene Daten. Übernimm solche Platzhalter unverändert in deine "
    "Zusammenfassung, wenn du auf die betreffende Stelle Bezug nimmst. Erfinde niemals "
    "Namen oder Details für diese Platzhalter und entferne sie nicht. "
    "Erstelle eine prägnante, gut strukturierte Zusammenfassung: ein kurzer Absatz mit "
    "den wichtigsten Punkten und, falls es der Inhalt hergibt, zusätzlich einige "
    "Stichpunkte mit Kernfakten. Antworte ausschließlich mit der Zusammenfassung, ohne "
    "Einleitung oder Meta-Kommentar."
)

_SYSTEM_ANONYMIZED_COMPACT_EN = (
    "You are an assistant that summarizes already-anonymized text. "
    "The input text has already been anonymized: bracketed placeholders such as "
    "[PERSON], [EMAIL_ADDRESS], or [ORGANIZATION] are intentional redactions standing "
    "in for removed personal data. Preserve these placeholders verbatim whenever you "
    "refer to the corresponding detail. Never invent names or details for these "
    "placeholders and never remove them. "
    "Produce a concise, well-structured summary: a short paragraph covering the key "
    "points and, if the content warrants it, a few bullet points of key facts. Respond "
    "with only the summary, no preamble or meta-commentary."
)

_SYSTEM_RAW_COMPACT_DE = (
    "Du bist ein Assistent, der Texte zusammenfasst. "
    "Erstelle eine prägnante, gut strukturierte Zusammenfassung des folgenden Textes: "
    "ein kurzer Absatz mit den wichtigsten Punkten und, falls es der Inhalt hergibt, "
    "zusätzlich einige Stichpunkte mit Kernfakten. Antworte ausschließlich mit der "
    "Zusammenfassung, ohne Einleitung oder Meta-Kommentar."
)

_SYSTEM_RAW_COMPACT_EN = (
    "You are an assistant that summarizes text. "
    "Produce a concise, well-structured summary of the following text: a short "
    "paragraph covering the key points and, if the content warrants it, a few bullet "
    "points of key facts. Respond with only the summary, no preamble or meta-commentary."
)

_SYSTEM_ANONYMIZED_DETAILED_DE = (
    "Du bist ein Assistent, der bereits anonymisierte Texte zusammenfasst. "
    "Der Eingabetext wurde bereits anonymisiert: eckige Platzhalter wie [PERSON], "
    "[EMAIL_ADDRESS] oder [ORGANIZATION] sind absichtliche Schwärzungen und stehen für "
    "entfernte personenbezogene Daten. Übernimm solche Platzhalter unverändert in deine "
    "Zusammenfassung, wenn du auf die betreffende Stelle Bezug nimmst. Erfinde niemals "
    "Namen oder Details für diese Platzhalter und entferne sie nicht. "
    "Erstelle eine ausführliche, strukturierte Zusammenfassung in zwei Teilen: Beginne mit "
    "einer Liste \"Kernaussagen\" — knappe Stichpunkte mit den wichtigsten Aussagen des "
    "Dokuments. Danach folgt eine ausführlichere, in thematische Abschnitte mit "
    "Zwischenüberschriften gegliederte Zusammenfassung, die relevante Details, "
    "Zusammenhänge und Hintergründe abdeckt, die in den Kernaussagen keinen Platz hatten. "
    "Antworte ausschließlich mit der Zusammenfassung (Markdown-Formatierung für "
    "Überschriften/Stichpunkte ist erwünscht), ohne Einleitung oder Meta-Kommentar."
)

_SYSTEM_ANONYMIZED_DETAILED_EN = (
    "You are an assistant that summarizes already-anonymized text. "
    "The input text has already been anonymized: bracketed placeholders such as "
    "[PERSON], [EMAIL_ADDRESS], or [ORGANIZATION] are intentional redactions standing "
    "in for removed personal data. Preserve these placeholders verbatim whenever you "
    "refer to the corresponding detail. Never invent names or details for these "
    "placeholders and never remove them. "
    "Produce a detailed, structured summary in two parts: start with a \"Key Takeaways\" "
    "bullet list covering the document's most important points, followed by a more "
    "thorough summary organized into thematic sections with subheadings, covering "
    "relevant details, context, and connections that didn't fit in the key takeaways. "
    "Respond with only the summary (markdown formatting for headings/bullets is "
    "welcome), no preamble or meta-commentary."
)

_SYSTEM_RAW_DETAILED_DE = (
    "Du bist ein Assistent, der Texte zusammenfasst. "
    "Erstelle eine ausführliche, strukturierte Zusammenfassung des folgenden Textes in "
    "zwei Teilen: Beginne mit einer Liste \"Kernaussagen\" — knappe Stichpunkte mit den "
    "wichtigsten Aussagen des Textes. Danach folgt eine ausführlichere, in thematische "
    "Abschnitte mit Zwischenüberschriften gegliederte Zusammenfassung, die relevante "
    "Details, Zusammenhänge und Hintergründe abdeckt, die in den Kernaussagen keinen "
    "Platz hatten. Antworte ausschließlich mit der Zusammenfassung (Markdown-Formatierung "
    "für Überschriften/Stichpunkte ist erwünscht), ohne Einleitung oder Meta-Kommentar."
)

_SYSTEM_RAW_DETAILED_EN = (
    "You are an assistant that summarizes text. "
    "Produce a detailed, structured summary of the following text in two parts: start "
    "with a \"Key Takeaways\" bullet list covering the text's most important points, "
    "followed by a more thorough summary organized into thematic sections with "
    "subheadings, covering relevant details, context, and connections that didn't fit "
    "in the key takeaways. Respond with only the summary (markdown formatting for "
    "headings/bullets is welcome), no preamble or meta-commentary."
)

_PROMPTS = {
    (True, SummaryStyle.COMPACT): (_SYSTEM_ANONYMIZED_COMPACT_DE, _SYSTEM_ANONYMIZED_COMPACT_EN),
    (True, SummaryStyle.DETAILED): (_SYSTEM_ANONYMIZED_DETAILED_DE, _SYSTEM_ANONYMIZED_DETAILED_EN),
    (False, SummaryStyle.COMPACT): (_SYSTEM_RAW_COMPACT_DE, _SYSTEM_RAW_COMPACT_EN),
    (False, SummaryStyle.DETAILED): (_SYSTEM_RAW_DETAILED_DE, _SYSTEM_RAW_DETAILED_EN),
}


def summarize_text(
    text: str, language: str, anonymized: bool = True, style: SummaryStyle = SummaryStyle.COMPACT
) -> str:
    is_de = language.lower().startswith("de")
    system_de, system_en = _PROMPTS[(anonymized, style)]
    system = system_de if is_de else system_en
    return generate(prompt=text, system=system).strip()
