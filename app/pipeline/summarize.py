"""Summarization of already-anonymized text via the local Ollama model."""

from __future__ import annotations

from app.llm.ollama_client import generate

_SYSTEM_DE = (
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

_SYSTEM_EN = (
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


def summarize_text(anonymized_text: str, language: str) -> str:
    system = _SYSTEM_DE if language.lower().startswith("de") else _SYSTEM_EN
    return generate(prompt=anonymized_text, system=system).strip()
