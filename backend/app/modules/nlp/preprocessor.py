"""
backend/app/modules/nlp/preprocessor.py

Medical NLP preprocessing pipeline for Aarogya AI.
Uses two spaCy models in a cascade:
  1. en_ner_bc5cdr_md  — BC5CDR-trained model for DISEASE and CHEMICAL entities
  2. en_core_sci_sm    — General biomedical model for everything else

Main exports:
  extract_symptoms(text: str) -> dict
  detect_disease_history(text: str) -> list[str]

Models are loaded ONCE at module level to keep Lambda cold starts cheap.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Model loading ────────────────────────────────────────────────────────────
# Load at module level — only once per Lambda instance.

_bc5cdr_nlp = None
_sci_nlp = None


def _load_models() -> None:
    """Lazy-load both spaCy models on first use."""
    global _bc5cdr_nlp, _sci_nlp
    if _bc5cdr_nlp is not None:
        return  # already loaded

    try:
        import spacy

        logger.info("Loading en_ner_bc5cdr_md …")
        _bc5cdr_nlp = spacy.load("en_ner_bc5cdr_md")
        logger.info("Loading en_core_sci_sm …")
        _sci_nlp = spacy.load("en_core_sci_sm")
        logger.info("Both spaCy models loaded successfully.")
    except OSError as exc:
        logger.warning(
            "spaCy models not installed (%s). "
            "NLP features will return empty results. "
            "Run: pip install https://…/en_ner_bc5cdr_md-0.5.4.tar.gz "
            "and pip install https://…/en_core_sci_sm-0.5.4.tar.gz",
            exc,
        )


# ── Constants ────────────────────────────────────────────────────────────────

_NEGATION_TOKENS = frozenset({"no", "not", "without", "denies", "never", "deny"})
_UNCERTAINTY_TOKENS = frozenset(
    {
        "possible",
        "possibly",
        "maybe",
        "might",
        "could",
        "suspected",
        "likely",
        "probable",
        "probably",
        "questionable",
        "perhaps",
    }
)
_SEVERITY_MAP = {
    "mild": "mild",
    "slight": "mild",
    "minor": "mild",
    "moderate": "moderate",
    "significant": "moderate",
    "severe": "severe",
    "severe pain": "severe",
    "excruciating": "severe",
    "extreme": "severe",
    "very severe": "severe",
    "intense": "severe",
}

# Regex to capture duration phrases like "for 3 days", "since 2 weeks", "2 months"
_DURATION_PATTERN = re.compile(
    r"(?:for|since|last|past)?\s*"
    r"(\d+(?:\.\d+)?)\s*"
    r"(hour|hours|hr|hrs|day|days|week|weeks|month|months|year|years)",
    re.IGNORECASE,
)

# Disease history patterns — group(1) captures ONLY the disease name (not the prefix)
_HISTORY_PATTERNS = [
    re.compile(
        r"history\s+of\s+([a-z][a-z\s\-]{2,40}?)(?=\s*(?:and|,|\.|;|$))", re.IGNORECASE
    ),
    re.compile(
        r"diagnosed\s+with\s+([a-z][a-z\s\-]{2,40}?)(?=\s*(?:and|,|\.|;|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:has|have|had)\s+([a-z][a-z\s\-]{2,40}?)(?=\s+for\s+\d|\s*(?:and|,|\.|;|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"known\s+case\s+of\s+([a-z][a-z\s\-]{2,40}?)(?=\s*(?:and|,|\.|;|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"chronic\s+([a-z][a-z\s\-]{2,40}?)(?=\s*(?:and|,|\.|;|$))", re.IGNORECASE
    ),
]

# Tokens that are commonly mis-tagged as entities — filtered out as noise
_NOISE_TOKENS = frozenset(
    {
        # pronouns / articles
        "i",
        "me",
        "my",
        "he",
        "she",
        "it",
        "we",
        "they",
        "you",
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        # duration words (picked up by sci model)
        "day",
        "days",
        "week",
        "weeks",
        "month",
        "months",
        "year",
        "years",
        "hour",
        "hours",
        "hr",
        "hrs",
        # severity/modifier words that get tagged
        "mild",
        "moderate",
        "severe",
        "severe pain",
        "excruciating",
        "slight",
        "minor",
        "significant",
        "intense",
        "extreme",
        # common words mistakenly tagged
        "patient",
        "patients",
        "history",
        "case",
        "cases",
        "symptoms",
        "symptom",
        "condition",
        "conditions",
        "possible",
        "possibly",
        "maybe",
        "might",
        "could",
        "chronic",
        "acute",
        "past",
        "since",
        "for",
    }
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _is_negated(token, doc) -> bool:
    """
    Check whether a spaCy token is negated.
    Strategy: walk the dependency tree up to 3 hops; if any ancestor or
    left-sibling within the sentence window carries a negation word, return True.
    """
    # Check left context window (up to 6 tokens to the left) for negation words
    start = max(0, token.i - 6)
    left_tokens = [doc[i].lower_ for i in range(start, token.i)]
    if any(t in _NEGATION_TOKENS for t in left_tokens):
        return True

    # Check dependency children of the token's head for neg relation
    if token.dep_ == "nsubj" or token.head.i != token.i:
        for child in token.head.children:
            if child.dep_ == "neg" or child.lower_ in _NEGATION_TOKENS:
                return True

    return False


def _is_uncertain(token, doc) -> bool:
    """
    Check if an entity is preceded by uncertainty markers within 5 tokens.
    """
    start = max(0, token.i - 5)
    window = [doc[i].lower_ for i in range(start, token.i)]
    return any(t in _UNCERTAINTY_TOKENS for t in window)


def _extract_severity(span, doc) -> Optional[str]:
    """
    Look for severity qualifiers within 4 tokens of the entity.
    """
    start = max(0, span.start - 4)
    end = min(len(doc), span.end + 4)
    window_text = doc[start:end].text.lower()
    for phrase, sev_level in sorted(_SEVERITY_MAP.items(), key=lambda x: -len(x[0])):
        if phrase in window_text:
            return sev_level
    return None


def _extract_duration(text: str):
    """
    Return (duration_string, duration_category) from anywhere in the text.
    Categories: acute (<7 days), subacute (7–30 days), chronic (>30 days).
    """
    match = _DURATION_PATTERN.search(text)
    if not match:
        return None, None

    value = float(match.group(1))
    unit = match.group(2).lower().rstrip("s")  # normalise to singular

    # Convert everything to days
    unit_to_days = {
        "hour": 1 / 24,
        "hr": 1 / 24,
        "day": 1,
        "week": 7,
        "month": 30,
        "year": 365,
    }
    days = value * unit_to_days.get(unit, 1)

    duration_str = match.group(0).strip()

    if days < 7:
        category = "acute"
    elif days <= 30:
        category = "subacute"
    else:
        category = "chronic"

    return duration_str, category


def _is_noise_entity(span) -> bool:
    """
    Return True if this entity span is a noise/false-positive.
    Filters out:
      - Single characters or pure digits
      - Stop words, pronouns, severity adjectives, duration words
      - Spans longer than 5 words (likely a sentence fragment, not an entity)
    """
    text = span.text.strip()
    lower = text.lower()

    # Single char or digit-only
    if len(text) <= 1 or text.isdigit():
        return True

    # Too long (sentence fragments)
    if len(text.split()) > 5:
        return True

    # Known noise tokens
    if lower in _NOISE_TOKENS:
        return True

    # Pure punctuation or whitespace
    if not any(c.isalpha() for c in text):
        return True

    return False


def _entity_to_dict(span, doc) -> dict:
    """Convert a spaCy entity span to the Aarogya symptom schema."""
    token = span.root
    duration_str, duration_category = _extract_duration(span.sent.text)
    return {
        "text": span.text,
        "canonical_form": span.text,  # overwritten by symptom_normalizer
        "label": span.label_,
        "body_part": None,  # filled by caller if BODY_PART detected
        "negated": _is_negated(token, doc),
        "uncertain": _is_uncertain(token, doc),
        "severity": _extract_severity(span, doc),
        "duration": duration_str,
        "duration_category": duration_category,
    }


# ── Public API ───────────────────────────────────────────────────────────────


def extract_symptoms(text: str) -> dict:
    """
    Run both scispaCy models on *text* and return a structured extraction.

    Returns:
        {
            "extracted_symptoms": [ { text, canonical_form, label, body_part,
                                      negated, uncertain, severity, duration,
                                      duration_category }, … ],
            "disease_history_mentions": ["diabetes", …],
            "raw_text": <original text>,
            "confidence": <float 0-1>,
        }

    Gracefully returns an empty result for empty/None input.
    """
    if not text or not text.strip():
        logger.debug("extract_symptoms received empty text — returning empty result.")
        return {
            "extracted_symptoms": [],
            "disease_history_mentions": [],
            "raw_text": text or "",
            "confidence": 0.0,
        }

    _load_models()

    # ── Collect all candidate spans from both models ──────────────────────────
    # We gather everything first, then sort by span length (longer = more specific)
    # and greedily select non-overlapping spans. This ensures "Back pain" wins
    # over "pain", and "chest pain" wins over "No chest pain".
    all_candidates: list[tuple] = []  # (ent, doc)

    if _bc5cdr_nlp is not None:
        try:
            doc_bc5cdr = _bc5cdr_nlp(text)
            for ent in doc_bc5cdr.ents:
                if not _is_noise_entity(ent):
                    all_candidates.append((ent, doc_bc5cdr))
        except Exception:
            logger.exception("BC5CDR model failed on input.")

    if _sci_nlp is not None:
        try:
            doc_sci = _sci_nlp(text)
            for ent in doc_sci.ents:
                if not _is_noise_entity(ent):
                    all_candidates.append((ent, doc_sci))
        except Exception:
            logger.exception("SciSpaCy general model failed on input.")

    # Sort by span length descending so longer, more specific spans are chosen first
    all_candidates.sort(key=lambda x: -(x[0].end_char - x[0].start_char))

    # ── Greedy non-overlapping span selection ─────────────────────────────────
    covered_spans: list[tuple[int, int]] = []
    seen_texts: set[str] = set()
    symptoms: list[dict] = []

    def _overlaps(start: int, end: int) -> bool:
        """Return True if [start, end) overlaps with any already-accepted span."""
        for cs, ce in covered_spans:
            if not (end <= cs or start >= ce):  # intervals intersect
                return True
        return False

    for ent, doc in all_candidates:
        start, end = ent.start_char, ent.end_char
        key = ent.text.lower().strip()
        if key not in seen_texts and not _overlaps(start, end):
            seen_texts.add(key)
            covered_spans.append((start, end))
            symptoms.append(_entity_to_dict(ent, doc))

    # ── Annotate body parts ───────────────────────────────────────────────────
    body_anatomy_hints = {
        "chest",
        "abdomen",
        "stomach",
        "back",
        "head",
        "throat",
        "neck",
        "shoulder",
        "arm",
        "leg",
        "knee",
        "ankle",
        "foot",
        "hand",
        "wrist",
        "elbow",
        "hip",
        "pelvis",
        "spine",
        "lung",
        "heart",
        "liver",
        "kidney",
        "ear",
        "eye",
        "nose",
        "mouth",
        "skin",
        "joint",
        "muscle",
        "bone",
    }
    for ent_dict in symptoms:
        for part in body_anatomy_hints:
            if part in ent_dict["text"].lower():
                ent_dict["body_part"] = part
                break

    # Confidence heuristic: fraction of input words covered by extracted entities
    word_count = max(len(text.split()), 1)
    covered = sum(len(s["text"].split()) for s in symptoms)
    confidence = min(covered / word_count, 1.0)

    result = {
        "extracted_symptoms": symptoms,
        "disease_history_mentions": detect_disease_history(text),
        "raw_text": text,
        "confidence": round(confidence, 4),
    }
    logger.info(
        "extract_symptoms: %d entities extracted (confidence=%.2f)",
        len(symptoms),
        confidence,
    )
    return result


def detect_disease_history(text: str) -> list[str]:
    """
    Extract past medical history mentions from *text* using regex patterns.

    Looks for:
      - "history of X"
      - "diagnosed with X"
      - "has / had / have X"
      - "known case of X"
      - "chronic X"

    Returns a deduplicated list of disease/condition strings.
    """
    if not text or not text.strip():
        return []

    _HISTORY_STOP = {"the", "and", "for", "his", "her", "this", "that", "a", "an"}

    found: set[str] = set()
    for pattern in _HISTORY_PATTERNS:
        for match in pattern.finditer(text):
            # group(1) is always just the disease name (prefix stripped by regex)
            entity = match.group(1).strip().lower()

            # If the has/have/had pattern captured "history of X", strip the prefix
            for prefix in (
                "history of ",
                "known case of ",
                "chronic ",
                "diagnosis of ",
                "diagnosed with ",
            ):
                if entity.startswith(prefix):
                    entity = entity[len(prefix) :].strip()

            # Strip trailing filler words that regex sometimes captures
            for filler in (" and", " or", " with", " the"):
                if entity.endswith(filler):
                    entity = entity[: -len(filler)].strip()

            # Filter very short or stop-word-only fragments
            if len(entity) >= 3 and entity not in _HISTORY_STOP:
                found.add(entity)

    logger.debug("detect_disease_history: %s", found)
    return sorted(found)
