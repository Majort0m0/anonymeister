"""PII detection and redaction — the privacy boundary of the app.

This module's output (never the raw ingested text) is what may legally be
handed on to the LLM stages (deep_check, summarize). The AnalyzerEngine and
its NLP models are expensive to build, so they are constructed once, lazily,
and reused for every call.

Detection (`analyze`) and redaction (`apply_anonymization`) are deliberately
split: the app shows the user what categories were found before actually
redacting anything, so they can opt specific categories out of redaction.
"""

from __future__ import annotations

import re
import threading
from typing import Callable

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import PhoneRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from app.config import (
    DEFAULT_LANGUAGE,
    RELEVANT_ID_COUNTRIES,
    SPACY_MODELS,
    SUPPORTED_PHONE_REGIONS,
)
from app.pipeline.pseudonymize import make_person_pseudonymizer
from app.schemas import AnonymizeResult, DetectedCategory, PiiEntity

_analyzer: AnalyzerEngine | None = None
_anonymizer = AnonymizerEngine()
_build_lock = threading.Lock()

_MAX_SAMPLES_PER_CATEGORY = 3
_POSTAL_CODE_SCORE = 0.85

# Presidio ships no generic postal-code recognizer, and a plain "digits
# followed by a capitalized word" pattern is far too noisy in German: every
# noun is capitalized, so things like "54321 Stück" or "12345 Einheiten"
# false-positive constantly. Instead, a 4-5 digit run is only treated as a
# postal code if it sits immediately before a span spaCy's NER already
# recognized as a LOCATION (the actual "<PLZ> <Ort>" address convention) —
# requiring an NER-confirmed place name is a much stronger signal than
# capitalization alone.
_DIGITS_BEFORE_LOCATION_RE = re.compile(r"(?<!\d)(\d{4,5})(?!\d)\s+$")


def _find_postal_codes(text: str, results: list) -> list:
    postal_codes = []
    for result in results:
        if result.entity_type != "LOCATION":
            continue
        match = _DIGITS_BEFORE_LOCATION_RE.search(text[: result.start])
        if match:
            postal_codes.append(
                RecognizerResult(
                    entity_type="POSTAL_CODE",
                    start=match.start(1),
                    end=match.end(1),
                    score=_POSTAL_CODE_SCORE,
                )
            )
    return postal_codes


def _missing_model_error(exc: OSError) -> RuntimeError:
    message = str(exc)
    for model_name in SPACY_MODELS.values():
        if model_name in message:
            return RuntimeError(
                f"Missing spaCy model '{model_name}'. Install it with: "
                f"python -m spacy download {model_name}"
            )
    hints = " ; ".join(f"python -m spacy download {m}" for m in SPACY_MODELS.values())
    return RuntimeError(
        "A required spaCy model is missing. Install the configured models with: "
        f"{hints}"
    )


def _build_analyzer() -> AnalyzerEngine:
    supported_languages = list(SPACY_MODELS.keys())

    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": lang, "model_name": model_name}
            for lang, model_name in SPACY_MODELS.items()
        ],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()

    try:
        nlp_engine.load()
    except OSError as exc:
        raise _missing_model_error(exc) from exc

    registry = RecognizerRegistry(supported_languages=supported_languages)
    registry.load_predefined_recognizers(
        languages=supported_languages,
        nlp_engine=nlp_engine,
        countries=RELEVANT_ID_COUNTRIES,
    )

    registry.remove_recognizer("PhoneRecognizer")
    for lang in supported_languages:
        registry.add_recognizer(
            PhoneRecognizer(
                supported_language=lang,
                supported_regions=SUPPORTED_PHONE_REGIONS,
            )
        )

    return AnalyzerEngine(
        nlp_engine=nlp_engine,
        registry=registry,
        supported_languages=supported_languages,
    )


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        with _build_lock:
            if _analyzer is None:
                _analyzer = _build_analyzer()
    return _analyzer


def _resolve_overlaps(results: list) -> list:
    """Greedily keep the highest-scoring, non-overlapping spans.

    Presidio's own cross-type conflict handling drops one side of an overlap
    based on iteration order (effectively: whichever span ends later wins),
    not confidence — so a stray low-score NER false positive can silently
    swallow a high-score, checksum-validated match (e.g. an IBAN). This
    resolves overlaps ourselves, by score, before anonymizing.
    """
    ordered = sorted(results, key=lambda r: (-r.score, r.start))
    selected: list = []
    for candidate in ordered:
        if not any(candidate.start < s.end and s.start < candidate.end for s in selected):
            selected.append(candidate)
    return sorted(selected, key=lambda r: r.start)


def resolve_language(language: str) -> str:
    return language if language in SPACY_MODELS else DEFAULT_LANGUAGE


def analyze(text: str, language: str) -> list:
    """Detect PII without redacting anything yet.

    Returns Presidio RecognizerResult objects (overlap-resolved by score).
    These are plain in-memory objects, not pydantic models — callers keep
    them server-side (see app.server's token cache) rather than serializing
    them to the frontend; only `summarize_categories()`'s output crosses the
    HTTP boundary.
    """
    lang = resolve_language(language)
    analyzer = _get_analyzer()
    raw_results = analyzer.analyze(text=text, language=lang)
    if not raw_results:
        return []

    resolved = _resolve_overlaps(raw_results)
    postal_codes = _find_postal_codes(text, resolved)
    return _resolve_overlaps(resolved + postal_codes) if postal_codes else resolved


def summarize_categories(text: str, results: list, source: str = "presidio") -> list[DetectedCategory]:
    """Aggregate detection results into counts + example snippets per category,
    for the pre-finalize review UI."""
    by_type: dict[str, list[str]] = {}
    for result in results:
        by_type.setdefault(result.entity_type, []).append(text[result.start:result.end])

    categories = []
    for entity_type, snippets in by_type.items():
        seen: list[str] = []
        for snippet in snippets:
            if snippet not in seen:
                seen.append(snippet)
            if len(seen) >= _MAX_SAMPLES_PER_CATEGORY:
                break
        categories.append(
            DetectedCategory(
                category=entity_type,
                count=len(snippets),
                source=source,
                samples=seen,
                is_person=(source == "presidio" and entity_type == "PERSON"),
            )
        )
    return categories


def apply_anonymization(
    text: str,
    results: list,
    excluded_types: set[str] | None = None,
    pseudonymize_person: bool = False,
    person_pseudonymizer: Callable[[str], str] | None = None,
) -> AnonymizeResult:
    """Redact `results`, skipping any whose entity_type is in `excluded_types`
    (left as original text) and, if `pseudonymize_person` is set, replacing
    PERSON matches with a consistent fake name instead of "[PERSON]".

    Pass an existing `person_pseudonymizer` (from `make_person_pseudonymizer()`)
    when this is called multiple times for the same document/export — e.g. once
    for the markdown transcript and once per cell for a structured-format
    re-export — so the same real name maps to the same fake name everywhere. If
    omitted, a fresh one is created (consistent only within this single call).
    """
    excluded_types = excluded_types or set()
    filtered = [r for r in results if r.entity_type not in excluded_types]

    if not filtered:
        return AnonymizeResult(anonymized_text=text, entities=[])

    counts: dict[str, int] = {}
    for result in filtered:
        counts[result.entity_type] = counts.get(result.entity_type, 0) + 1

    if pseudonymize_person and "PERSON" in counts and person_pseudonymizer is None:
        person_pseudonymizer = make_person_pseudonymizer()

    operators: dict[str, OperatorConfig] = {}
    for entity_type in counts:
        if entity_type == "PERSON" and pseudonymize_person and person_pseudonymizer is not None:
            operators[entity_type] = OperatorConfig("custom", {"lambda": person_pseudonymizer})
        else:
            operators[entity_type] = OperatorConfig("replace", {"new_value": f"[{entity_type}]"})

    anonymized = _anonymizer.anonymize(text=text, analyzer_results=filtered, operators=operators)

    # Count from anonymized.items (the replacements actually applied after Presidio's
    # own overlap resolution), not the raw analyzer results, which can contain
    # overlapping candidate detections that never make it into the output text.
    applied_counts: dict[str, int] = {}
    for item in anonymized.items:
        applied_counts[item.entity_type] = applied_counts.get(item.entity_type, 0) + 1

    entities = [
        PiiEntity(entity_type=entity_type, count=count, source="presidio")
        for entity_type, count in applied_counts.items()
    ]

    return AnonymizeResult(anonymized_text=anonymized.text, entities=entities)
