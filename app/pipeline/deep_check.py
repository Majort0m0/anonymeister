"""Second-pass PII detection over text the deterministic Presidio pass already redacted.

Privacy invariant: every function in this module must only ever be called
with text that has already gone through the Presidio anonymization pass
(placeholders like [PERSON] or [EMAIL_ADDRESS] already in place). The raw
original document must never reach this module or be sent to the local
model — this pass exists purely to catch indirect identifiers (nicknames,
role-based references, project codenames, ...) that the deterministic pass
cannot resolve.

The flow is split into three steps so the caller can show the user what was
found (as categories with counts) before anything is actually redacted:

1. find_candidates()               - runs the LLM pass, returns raw candidate
                                      substrings + normalized categories.
2. summarize_candidate_categories() - aggregates candidates into the
                                      DetectedCategory rows the review UI shows.
3. apply_candidates()              - actually performs the redaction, honoring
                                      any categories the user chose to exclude.
"""

from __future__ import annotations

import json
import re

from app.llm.ollama_client import generate
from app.schemas import AnonymizeResult, DetectedCategory, PiiEntity

_SYSTEM_DE = (
    "Du bist ein Datenschutz-Experte. Der folgende Text wurde bereits automatisch "
    "anonymisiert: direkte Namen, Adressen, E-Mails usw. sind bereits durch Platzhalter "
    "wie [PERSON] oder [EMAIL_ADDRESS] ersetzt. Deine Aufgabe ist es, verbleibende "
    "Hinweise zu finden, die eine Person trotzdem identifizierbar machen könnten: "
    "Spitznamen, Rollenbezeichnungen (z. B. \"der Teamleiter\", \"die Assistentin von X\"), "
    "indirekte Verweise, Projekt- oder Decknamen, oder andere kontextabhängige Hinweise. "
    "Antworte AUSSCHLIESSLICH mit einem JSON-Array von Objekten der Form "
    '{"text": "<exakte Textstelle>", "category": "<kurze Kategorie>"}. '
    "Wenn nichts gefunden wird, antworte mit einem leeren Array []. "
    "Gib keinerlei zusätzlichen Text, keine Erklärungen und keine Code-Blöcke aus."
)

_SYSTEM_EN = (
    "You are a privacy expert. The following text has already been automatically "
    "anonymized: direct names, addresses, emails etc. have already been replaced with "
    "placeholders such as [PERSON] or [EMAIL_ADDRESS]. Your job is to find any remaining "
    "clues that could still identify a person: nicknames, role-based identifiers "
    "(e.g. \"the team lead\", \"X's assistant\"), indirect references, project or code "
    "names, or other context-dependent hints. "
    'Respond ONLY with a JSON array of objects of the form {"text": "<exact substring>", '
    '"category": "<short category label>"}. '
    "If nothing is found, respond with an empty array []. "
    "Do not output any additional text, explanations, or code blocks."
)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
_NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]+")


def _extract_json_array(response: str) -> list | None:
    fenced = _CODE_FENCE_RE.search(response)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        bare = _JSON_ARRAY_RE.search(response)
        candidate = bare.group(0) if bare else None
    if candidate is None:
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def _normalize_category(category: str) -> str:
    normalized = _NON_ALNUM_RE.sub("_", category.strip()).strip("_").upper()
    return normalized or "PII"


def find_candidates(anonymized_text: str, language: str) -> list[dict]:
    """Run the LLM deep-check pass and return validated candidate substrings.

    `anonymized_text` must already be the output of the Presidio pass (see
    module docstring) — this function never sees, and must never be given,
    the raw original document.

    Returns a list of {"text": <original candidate substring>, "category":
    <normalized UPPER_SNAKE_CASE category>, "count": <occurrences found in
    anonymized_text>} dicts, sorted by substring length descending (so a
    short match doesn't get consumed by redacting a longer overlapping one
    first when these are later applied). On any parse failure, or when no
    candidate actually occurs in the text, this degrades gracefully by
    dropping/omitting rather than raising.
    """
    system = _SYSTEM_DE if language.lower().startswith("de") else _SYSTEM_EN
    response = generate(prompt=anonymized_text, system=system)

    items = _extract_json_array(response)
    if items is None:
        return []

    raw_candidates: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_text = item.get("text")
        raw_category = item.get("category")
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        if not isinstance(raw_category, str) or not raw_category.strip():
            continue
        raw_candidates.append((raw_text, raw_category))

    candidates: list[dict] = []
    for raw_text, raw_category in raw_candidates:
        occurrences = anonymized_text.count(raw_text)
        if occurrences == 0:
            continue
        candidates.append(
            {
                "text": raw_text,
                "category": _normalize_category(raw_category),
                "count": occurrences,
            }
        )

    # Longer substrings first so a short match (e.g. a surname) doesn't
    # consume part of a longer one (e.g. "role + surname") before it is
    # checked, once these candidates are later applied.
    candidates.sort(key=lambda c: len(c["text"]), reverse=True)
    return candidates


def summarize_candidate_categories(candidates: list[dict]) -> list[DetectedCategory]:
    """Aggregate find_candidates() output into review-UI-ready categories.

    Every row here is a deep-check finding: source="llm_deep_check" and
    is_person=False always (deep-check never touches Presidio's PERSON
    category — its findings are free-form labels like "SPITZNAME" or
    "ROLLENBEZEICHNUNG").
    """
    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    order: list[str] = []

    for candidate in candidates:
        category = candidate["category"]
        text = candidate["text"]
        count = candidate["count"]

        if category not in counts:
            counts[category] = 0
            samples[category] = []
            order.append(category)
        counts[category] += count
        if text not in samples[category] and len(samples[category]) < 3:
            samples[category].append(text)

    return [
        DetectedCategory(
            category=category,
            count=counts[category],
            source="llm_deep_check",
            samples=samples[category],
            is_person=False,
        )
        for category in order
    ]


def apply_candidates(
    text: str,
    candidates: list[dict],
    excluded_categories: set | None = None,
) -> AnonymizeResult:
    """Actually redact find_candidates() output against `text`.

    `text` may not be byte-identical to whatever find_candidates() originally
    ran on (the user may have excluded some Presidio categories between the
    "analyze" and "finalize" steps, changing surrounding text), so occurrence
    counts are re-derived from `text` here rather than trusting the stored
    "count". A candidate whose category is in `excluded_categories` is left
    untouched; a candidate that no longer occurs in `text` at all is skipped
    silently, matching this module's existing graceful-degradation behavior.

    `candidates` is expected in find_candidates()'s longest-substring-first
    order, which is preserved (not re-sorted) here.
    """
    excluded = excluded_categories or set()

    result_text = text
    counts: dict[str, int] = {}
    for candidate in candidates:
        category = candidate["category"]
        if category in excluded:
            continue

        raw_text = candidate["text"]
        occurrences = result_text.count(raw_text)
        if occurrences == 0:
            continue

        result_text = result_text.replace(raw_text, f"[{category}]")
        counts[category] = counts.get(category, 0) + occurrences

    entities = [
        PiiEntity(entity_type=category, count=count, source="llm_deep_check")
        for category, count in counts.items()
    ]
    return AnonymizeResult(anonymized_text=result_text, entities=entities)
