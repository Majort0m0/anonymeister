"""Context-based correction pass for raw audio transcripts.

Whisper's raw output can mishear individual words or short passages when the
source audio quality is poor (background noise, unclear pronunciation,
accents, overlapping speakers). This module asks the local LLM to fix only
such clear, contextually-implausible mis-transcriptions — never to rewrite,
shorten, or otherwise "improve" the text — before anything else touches it.

Deliberately NOT a rewrite/paraphrase pass: a model that changes prose style,
drops filler words/repetitions (normal in spoken language, not errors), or
shortens content would corrupt the transcript's fidelity to what was actually
said, which is the opposite of this feature's purpose. The prompts below are
written to constrain the model to narrow, surgical corrections.

Called unconditionally for every audio source from
app.pipeline.pipeline.analyze_file(), before analyze() ever runs — so
Presidio/deep-check PII detection benefits from the cleaned-up text too, and
so the "no anonymization" plain-transcript path gets a better transcript as
well (this has nothing to do with redaction, it runs regardless of
options.anonymize/options.deep_check). There is deliberately no user-facing
toggle for this (confirmed decision, see project history) — it's meant to be
a fixed part of how audio is processed, the same way postal-code detection
just "happens" as part of analysis rather than being an opt-in switch.

Sending the raw, unredacted transcript to the local LLM here follows the same
already-established precedent as deep_check.find_candidates() (see that
module's and app/pipeline/pipeline.py's docstrings): Ollama is always the
local, never-networked instance, so there's no privacy cost to it seeing raw
text before redaction — quite the opposite, redacting first would let
Presidio's own mistakes corrupt the very passages this pass needs to read
intact.

Chunking is its own, simpler scheme than deep_check.py's — deliberately NOT
reused:
- deep_check._split_into_chunks() splits on line boundaries with overlap,
  designed for extracting a JSON candidate list per chunk (independent
  per-chunk results are merged afterwards by exact text match). Whisper's
  output is one flat, newline-free string (see transcription.py), so a
  line-based splitter is a no-op against it; and this pass reconstructs
  continuous prose, where overlap would produce two independently-rewritten
  versions of the same passage with no clean way to merge them the way
  deduped JSON candidates can be.
- So: sentence-boundary-based, NON-overlapping chunks. A target chunk size
  smaller than deep_check's (900-1200 words vs. 1800) — deep_check's
  extraction task always returns compact JSON regardless of input size, but
  this task's output is close to 1:1 with its input (the full corrected text
  is echoed back), so a large input leaves much less headroom in
  OLLAMA_NUM_CTX before quality degrades near the context limit.

Ollama-unavailable handling is the one place this module departs from every
other LLM call site in the app (deep_check.py, summarize.py): those are all
gated behind an explicit user choice (the deep-check toggle, or choosing an
output mode that includes a summary) — if you opted in and Ollama isn't
there, a loud RuntimeError is a defensible contract. This pass runs for
EVERY audio file unconditionally, including for users who never installed
Ollama at all (the app is explicitly designed to work without it — see
Installationshinweise.md). A hard failure here would make audio
transcription itself start requiring Ollama, which would be a real
regression. `ollama_client.generate()`'s underlying `ollama.Client` is also
constructed with an unbounded timeout (confirmed by reading the installed
`ollama` package directly) — a fully-absent Ollama fails fast (connection
refused), but a reachable-but-unresponsive one (e.g. a misconfigured
OLLAMA_HOST) could hang indefinitely. So: only the first chunk is attempted
unconditionally; the moment any chunk raises RuntimeError, every remaining
chunk (including that one) is returned uncorrected with no further
generate() calls for the rest of this run — bounding worst-case exposure to
one hang per file while still degrading cleanly if Ollama dies partway
through a long transcript. This is handled entirely in this module;
app/llm/ollama_client.py itself (shared by deep_check.py and summarize.py,
whose loud-fail contract is correct for their own opt-in features) is
untouched.
"""

from __future__ import annotations

import re
from typing import Callable

from app.llm.ollama_client import generate

# Low, near-deterministic temperature — this is a conservative correction
# task, not creative generation (mirrors deep_check.py's
# _EXTRACTION_TEMPERATURE for the same reason: repeated runs should agree).
_CORRECTION_TEMPERATURE = 0.2

# Smaller than deep_check's 1800/2500 — see module docstring for why: this
# task's output is close to 1:1 with its input length, unlike deep_check's
# compact JSON output, so it needs more headroom in OLLAMA_NUM_CTX per chunk.
_CHUNK_TARGET_WORDS = 1000
_CHUNK_THRESHOLD_WORDS = 1300  # below this, a single call is not worth splitting

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def _split_into_chunks(
    text: str,
    target_words: int = _CHUNK_TARGET_WORDS,
    threshold_words: int = _CHUNK_THRESHOLD_WORDS,
) -> list[str]:
    """Split `text` into non-overlapping chunks along sentence boundaries
    (never mid-sentence) — see module docstring for why this differs from
    deep_check.py's line-based, overlapping chunker. Boundary detection is a
    plain regex, not a full sentence tokenizer (an abbreviation like "Dr."
    can occasionally split early) — acceptable here since a slightly early
    split only costs the model a little context at that one boundary, not
    correctness."""
    if len(text.split()) <= threshold_words:
        return [text]

    sentences = _SENTENCE_BOUNDARY_RE.split(text)
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        sentence_words = len(sentence.split())
        if current and current_words + sentence_words > target_words:
            chunks.append(" ".join(current))
            current = []
            current_words = 0
        current.append(sentence)
        current_words += sentence_words

    if current:
        chunks.append(" ".join(current))
    return chunks


_SYSTEM_DE = (
    "Du bist ein Experte für die Nachbearbeitung von Audio-Transkriptionen. Der folgende Text "
    "wurde automatisch per Spracherkennung aus einer Audioaufnahme transkribiert, deren Qualität "
    "schlecht gewesen sein kann (Hintergrundgeräusche, undeutliche Aussprache, Akzent, mehrere "
    "sich überlappende Sprecher). Dadurch können einzelne Wörter oder kurze Passagen falsch "
    "erkannt worden sein. Deine einzige Aufgabe: solche offensichtlichen Erkennungsfehler zu "
    "korrigieren — Stellen, die im Kontext eindeutig unsinnig, grammatikalisch fehlerhaft oder "
    "inhaltlich widersprüchlich sind und plausibel auf ein falsch verstandenes, ähnlich "
    "klingendes Wort zurückgehen.\n\n"
    "Wichtige Einschränkungen:\n"
    "- Ändere NICHTS, wenn der Text bereits Sinn ergibt — auch nicht Stil, Wortwahl oder "
    "Satzbau, und auch nicht, wenn der Text umgangssprachlich, unvollständig, abgehackt oder "
    "wiederholend klingt (das ist normal für gesprochene Sprache, kein Fehler). Das gilt auch "
    "für ungewöhnliche, aber grammatisch gültige Konstruktionen (z. B. Konjunktiv-Nebensätze "
    "ohne \"dass\", wie \"er sagte, er habe Zeit\") — das ist kein Fehler und wird NICHT "
    "umformuliert, auch wenn eine andere Formulierung geläufiger wäre. Im Zweifel: nichts "
    "ändern.\n"
    "- Erfinde oder ergänze KEINE Informationen, die nicht eindeutig aus dem Kontext hervorgehen.\n"
    "- Entferne KEINE Inhalte — keine Füllwörter, Wiederholungen oder abgebrochenen Sätze. Das "
    "ist kein Lektorat, sondern ausschließlich eine Fehlerkorrektur einzelner Wörter/kurzer "
    "Passagen.\n"
    "- Ändere Namen, Orte, Firmen, Zahlen oder andere Eigennamen nur, wenn die vorliegende "
    "Schreibweise eindeutig unsinnig ist und du dir der korrekten Schreibweise sicher bist — im "
    "Zweifel unverändert lassen.\n"
    "- Enthält der Text keine erkennbaren Transkriptionsfehler, gib ihn exakt unverändert "
    "zurück.\n\n"
    "Antworte AUSSCHLIESSLICH mit dem (ggf. korrigierten) Text selbst — ohne Einleitung, "
    "Erklärung, Anführungszeichen oder Code-Block. Die Antwort muss in derselben Sprache wie der "
    "Eingabetext sein und im Wesentlichen dieselbe Länge haben."
)

_SYSTEM_EN = (
    "You are an expert at post-processing audio transcriptions. The following text was "
    "automatically transcribed from an audio recording whose quality may have been poor "
    "(background noise, unclear pronunciation, accents, multiple overlapping speakers). As a "
    "result, individual words or short passages may have been misrecognized. Your only job: "
    "correct such obvious recognition errors — spots that are clearly nonsensical, "
    "grammatically broken, or contextually contradictory in a way plausibly caused by a "
    "misheard, similar-sounding word.\n\n"
    "Important constraints:\n"
    "- Change NOTHING if the text already makes sense — not style, word choice, or sentence "
    "structure, even if it sounds colloquial, incomplete, choppy, or repetitive (that is normal "
    "for spoken language, not an error). This also applies to unusual but grammatically valid "
    "constructions (e.g. formal subjunctive reported speech) — that is not an error and must "
    "NOT be reworded, even if a different phrasing would be more common. When in doubt, change "
    "nothing.\n"
    "- Do NOT invent or add any information that isn't clearly implied by the context.\n"
    "- Do NOT remove any content — no filler words, repetitions, or broken-off sentences. This "
    "is not an editing pass, only a narrow correction of individual misheard words/short "
    "passages.\n"
    "- Only change names, places, companies, numbers, or other proper nouns if the given "
    "spelling is clearly nonsensical and you are confident of the correct spelling — when in "
    "doubt, leave unchanged.\n"
    "- If the text contains no recognizable transcription errors, return it exactly unchanged.\n\n"
    "Respond ONLY with the (possibly corrected) text itself — no preamble, explanation, "
    "quotation marks, or code block. The response must be in the same language as the input "
    "and roughly the same length."
)


def correct_transcript(
    raw_text: str,
    language: str,
    on_progress: Callable[[str, int, int], None] | None = None,
    on_plan: Callable[[list[tuple[str, int]]], None] | None = None,
) -> str:
    if not raw_text.strip():
        return raw_text

    chunks = _split_into_chunks(raw_text)
    if on_plan:
        on_plan([("transcript_correction", len(chunks))])

    system = _SYSTEM_DE if language.lower().startswith("de") else _SYSTEM_EN

    if on_progress:
        on_progress("transcript_correction", 0, len(chunks))

    corrected_chunks: list[str] = []
    ollama_unavailable = False
    for i, chunk in enumerate(chunks):
        if ollama_unavailable:
            corrected_chunks.append(chunk)
            continue
        try:
            corrected = generate(
                prompt=chunk, system=system, temperature=_CORRECTION_TEMPERATURE
            ).strip()
            corrected_chunks.append(corrected if corrected else chunk)
            if on_progress:
                on_progress("transcript_correction", i + 1, len(chunks))
        except RuntimeError:
            # See module docstring: this is the only LLM call in the app
            # with no user opt-in, so a failure degrades silently to the
            # uncorrected text instead of propagating. Deliberately does NOT
            # call on_progress for this failed attempt or any later skipped
            # chunk — both complete near-instantly with no real Ollama call
            # behind them, and reporting each as its own "chunk done" event
            # would feed a string of near-zero durations into
            # progress_calibration.py's per-chunk EMA, corrupting future
            # ETA estimates for this stage. A single jump straight to 100%
            # after the loop (below) keeps the progress bar honest without
            # polluting that average.
            ollama_unavailable = True
            corrected_chunks.append(chunk)

    if on_progress and ollama_unavailable:
        on_progress("transcript_correction", len(chunks), len(chunks))

    return " ".join(corrected_chunks)
