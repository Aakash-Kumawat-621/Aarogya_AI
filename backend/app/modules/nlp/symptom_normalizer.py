"""
backend/app/modules/nlp/symptom_normalizer.py

Maps extracted symptom entities to canonical forms using:
  1. Exact match against symptom_synonyms.json
  2. Fuzzy match fallback via rapidfuzz (score_cutoff=80)

Exports:
  normalize_symptom(text: str) -> dict
  normalize_all(symptom_entities: list) -> list
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Load synonym dictionary at module level ──────────────────────────────────

_SYNONYMS_PATH = Path(__file__).parent / "symptom_synonyms.json"

# Build lookup structures once
# _canonical_to_synonyms: { "chest pain": ["chest ache", "chest tightness", …], … }
# _synonym_to_canonical:   { "chest ache": "chest pain", … }
_canonical_to_synonyms: dict[str, list[str]] = {}
_synonym_to_canonical: dict[str, str] = {}


def _load_synonyms() -> None:
    """Load and invert the synonym dictionary from JSON (run once at module init)."""
    global _canonical_to_synonyms, _synonym_to_canonical

    try:
        raw = json.loads(_SYNONYMS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("symptom_synonyms.json not found at %s", _SYNONYMS_PATH)
        return
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse symptom_synonyms.json: %s", exc)
        return

    for canonical, synonyms in raw.items():
        if canonical.startswith("_"):
            # Skip metadata keys like _meta
            continue
        _canonical_to_synonyms[canonical] = [s.lower() for s in synonyms]
        # Map each synonym → canonical
        for syn in synonyms:
            _synonym_to_canonical[syn.lower()] = canonical
        # The canonical itself maps to itself
        _synonym_to_canonical[canonical.lower()] = canonical

    logger.info(
        "Loaded %d canonical symptoms with %d synonym mappings.",
        len(_canonical_to_synonyms),
        len(_synonym_to_canonical),
    )


# Run immediately on import
_load_synonyms()


# ── Public API ────────────────────────────────────────────────────────────────


def normalize_symptom(text: str) -> dict:
    """
    Attempt to map *text* to a canonical symptom name.

    Returns a dict:
        {
            "canonical": <str>,   # canonical form if matched, else original text
            "matched":   <bool>,
            "score":     <float>, # 100.0 for exact, 80–99 for fuzzy, 0 for miss
        }
    """
    if not text or not text.strip():
        return {"canonical": "", "matched": False, "score": 0.0}

    normalized = text.lower().strip()

    # 1. Exact match
    if normalized in _synonym_to_canonical:
        canonical = _synonym_to_canonical[normalized]
        logger.debug("Exact match: '%s' → '%s'", text, canonical)
        return {"canonical": canonical, "matched": True, "score": 100.0}

    # 2. Fuzzy match via rapidfuzz
    try:
        from rapidfuzz import fuzz
        from rapidfuzz import process as rf_process

        # Build flat list of all synonyms for search
        all_synonyms = list(_synonym_to_canonical.keys())
        result = rf_process.extractOne(
            normalized,
            all_synonyms,
            scorer=fuzz.WRatio,
            score_cutoff=80,
        )
        if result is not None:
            best_match, score, _ = result
            canonical = _synonym_to_canonical[best_match]
            logger.debug(
                "Fuzzy match: '%s' → '%s' (via '%s', score=%.1f)",
                text,
                canonical,
                best_match,
                score,
            )
            return {"canonical": canonical, "matched": True, "score": round(score, 2)}
    except ImportError:
        logger.warning("rapidfuzz not installed — skipping fuzzy matching.")

    # 3. No match — return original text unchanged
    logger.debug("No match for: '%s'", text)
    return {"canonical": text, "matched": False, "score": 0.0}


def normalize_all(symptom_entities: list[dict]) -> list[dict]:
    """
    Apply :func:`normalize_symptom` to a list of entity dicts
    produced by :mod:`preprocessor`.

    For each entity dict, the ``canonical_form`` field is updated with the
    resolved canonical name (or left as the raw text if no match found).
    A ``normalization`` sub-dict is attached for debugging.

    Returns the updated list (mutated in-place + returned for convenience).
    """
    for entity in symptom_entities:
        raw_text = entity.get("text", "")
        result = normalize_symptom(raw_text)
        entity["canonical_form"] = result["canonical"]
        entity["normalization"] = result  # for transparency / debugging
    return symptom_entities


def get_all_canonical_symptoms() -> list[str]:
    """Return all canonical symptom names (for autocomplete / reference)."""
    return sorted(_canonical_to_synonyms.keys())


def get_synonyms_for(canonical: str) -> list[str]:
    """Return all known synonyms for a given canonical symptom name."""
    return _canonical_to_synonyms.get(canonical.lower(), [])
