"""Claim categorization (FR / AC-CATEGORY-1..6).

Assigns each claim exactly one category: citation, mechanistic, or safety_critical.
The category drives downstream routing, so the safety cap must never depend on the
model getting the label right. Two guards enforce that:

- a deterministic lexical fail-safe runs first and forces ``safety_critical`` whenever
  the shared safety oracle fires (AC-CATEGORY-5), independently of the model, and
- every model failure mode (call error, unparseable output, or confidence below the
  configured floor) falls closed to ``safety_critical`` (AC-CATEGORY-5). A claim is
  never returned without a category.

The model only decides between citation and mechanistic once the safe cases are already
covered, and its ``safety_critical`` label still dominates (AC-CATEGORY-1).
"""

from __future__ import annotations

import json
import re

from ..config import SAFETY_SUBTYPES, Category, Config
from ..llm import LlmClient, LlmError
from ..prompt_safety import UNTRUSTED_DATA_RULE, wrap_untrusted
from ..safety import is_safety_critical_text

_SYSTEM = (
    "You are a classifier for scientific claims made in drug-discovery memos. "
    "Assign each claim exactly one category from this fixed set: "
    "citation, mechanistic, safety_critical. "
    "Use citation when the claim's substance is an attribution to a reference or "
    "source. Use safety_critical when the claim asserts a drug target, a dose or "
    "dosing regimen, or a clinical indication. Use mechanistic for a biological "
    "mechanism, pathway, or association that is none of the above. "
    "Respond with a single JSON object and nothing else, of the exact form "
    '{"category": "<one of citation|mechanistic|safety_critical>", '
    '"confidence": <number between 0 and 1>}.\n\n' + UNTRUSTED_DATA_RULE
)

_PROMPT_TEMPLATE = "Classify this claim:\n\n{claim}"

# Non-greedy match of the first balanced-looking JSON object in the response text.
_RE_JSON_OBJECT = re.compile(r"\{.*?\}", re.DOTALL)

_LABEL_TO_CATEGORY = {
    "citation": Category.CITATION,
    "mechanistic": Category.MECHANISTIC,
    "safety_critical": Category.SAFETY_CRITICAL,
}


def categorize(claim_text: str, llm: LlmClient, config: Config) -> Category:
    """Return the claim's category, failing closed to SAFETY_CRITICAL.

    Order of decision:
    1. Lexical fail-safe: if the deterministic safety oracle fires, return
       SAFETY_CRITICAL without calling the model (AC-CATEGORY-5).
    2. Ask the model to classify; its safety_critical label dominates (AC-CATEGORY-1).
    3. Any failure (call error, unparseable output, or confidence below
       config.categorizer_conf) falls closed to SAFETY_CRITICAL (AC-CATEGORY-5).
    """
    if is_safety_critical_text(claim_text):
        return Category.SAFETY_CRITICAL

    try:
        response = llm.complete(
            system=_SYSTEM,
            prompt=_PROMPT_TEMPLATE.format(claim=wrap_untrusted(claim_text)),
            temperature=0.0,
        )
    except LlmError:
        return Category.SAFETY_CRITICAL

    parsed = _parse(response.text)
    if parsed is None:
        return Category.SAFETY_CRITICAL

    category, confidence = parsed
    if category is Category.SAFETY_CRITICAL:
        return Category.SAFETY_CRITICAL
    if confidence < config.categorizer_conf:
        return Category.SAFETY_CRITICAL
    return category


def _parse(text: str) -> tuple[Category, float] | None:
    """Extract (category, confidence) from the model text, or None if unusable."""
    match = _RE_JSON_OBJECT.search(text)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    label = payload.get("category")
    category = _LABEL_TO_CATEGORY.get(label) if isinstance(label, str) else None
    if category is None:
        return None

    raw_conf = payload.get("confidence")
    if isinstance(raw_conf, bool) or not isinstance(raw_conf, (int, float)):
        return None
    return category, float(raw_conf)


def validate_taxonomy_config(config: Config) -> None:
    """Fail-closed startup guard for the safety taxonomy (AC-CATEGORY-6).

    Raise ValueError if the taxonomy that the safety cap rests on is broken: an empty
    set of safety sub-types, or a Category enum missing its SAFETY_CRITICAL member.
    """
    if not SAFETY_SUBTYPES:
        raise ValueError("SAFETY_SUBTYPES is empty; the safety taxonomy is broken.")
    if not hasattr(Category, "SAFETY_CRITICAL"):
        raise ValueError("Category has no SAFETY_CRITICAL member; the safety taxonomy is broken.")
