"""Independent lexical safety oracle (AC-CATEGORY-5 fail-safe, AC-SAFETY-4 guard).

Deterministic, no-LLM detection that a claim asserts a safety-critical fact: a target, a
dose or dosing regimen, or an indication. Used two ways so the safety cap never rests on
the model's category label:

- the categorizer forces ``safety_critical`` when this fires (a fail-safe default), and
- the severity stage re-derives safety-criticality from this same signal, independently of
  the model, before it will allow any auto-pass.

High recall is the design goal; false positives are acceptable because they only over-route
to a human. The lexicon covers the clear, unambiguous signals; the model categorizer plus
its recall floor handle the subtler cases.
"""

from __future__ import annotations

import re

# Dose: a number with a clinical unit, or explicit dosing vocabulary and frequencies.
# Full-word units are listed before their abbreviations so the longest match wins.
_RE_DOSE = re.compile(
    r"""
    \b\d+(?:\.\d+)?\s*
        (?:micrograms?|milligrams?|kilograms?|milliliters?|millilitres?|liters?|litres?
          |grams?|mcg|mg|ug|kg|ml|nmol|mmol|iu|units?|g|l)
        (?:\s*/\s*(?:kg|m2|day|dose|ml))?\b
    | \b(?:dose|dosed|doses|dosing|dosage|regimen|administered|administration|titrat\w+)\b
    | \b(?:bid|qd|tid|qid|q\d+h)\b
    | \b(?:once|twice|three\s+times)\s+(?:a\s+|per\s+)?(?:daily|day|week|weekly)\b
    | \bper\s+day\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Indication: what a drug is for.
_RE_INDICATION = re.compile(
    r"""
    \bindicated\s+for\b
    | \bindications?\b
    | \b(?:for\s+the\s+)?treatment\s+of\b
    | \bto\s+treat\b
    | \btherapy\s+for\b
    | \bfirst[-\s]?line\b | \bsecond[-\s]?line\b
    | \bapproved\s+for\b | \bprescribed\s+for\b
    | \bmanagement\s+of\b
    | \brecommended\s+(?:in|for)\b
    | \bcontraindicat\w+\b
    | \boff[-\s]?label\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Target: an assertion that a molecule acts on a specific target. Bare "pathway",
# "receptor", or "kinase" are excluded so generic mechanism is not swept in.
_RE_TARGET = re.compile(
    r"""
    \btarget(?:s|ing|ed)?\b
    | \binhibitor\s+of\b | \b\w+\s+inhibitor\b
    | \bantagonist\s+of\b | \bagonist\s+of\b
    | \bbinds?\s+to\b | \bacts?\s+on\b
    | \bselective\s+for\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Checked in this order; the first match names the sub-type.
_SUBTYPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dosing", _RE_DOSE),
    ("indication", _RE_INDICATION),
    ("target", _RE_TARGET),
)


def match_safety(text: str) -> tuple[bool, str | None]:
    """Return (matched, sub-type). Sub-type is one of dosing/indication/target, or None."""
    for subtype, pattern in _SUBTYPE_PATTERNS:
        if pattern.search(text):
            return True, subtype
    return False, None


def is_safety_critical_text(text: str) -> bool:
    return match_safety(text)[0]
