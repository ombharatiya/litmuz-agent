"""Deterministic metadata-match rules (AC-CITE-1/4/8). Pure functions, no I/O, no LLM.

- author_match: every claim-attributed surname is a member of the source surname set
  (subset test), case-folded and diacritics-stripped.
- title_match: normalized token-sort similarity >= threshold (default 0.95).
- year_match: exact membership in the source's {epub_year, print_year} set.

Absence of a claimed value yields NOT_APPLICABLE, never FALSE (AC-CITE-8), so a bare
identifier citation is never branded a metadata mismatch.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from ..config import MatchResult


def _fold(text: str) -> str:
    """Lower-case, strip diacritics, collapse to alphanumerics + single spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    stripped = stripped.casefold()
    return re.sub(r"[^a-z0-9\s]", " ", stripped)


def normalize_surname(name: str) -> str:
    return re.sub(r"\s+", " ", _fold(name)).strip()


def _title_tokens(title: str) -> str:
    tokens = sorted(t for t in _fold(title).split() if t)
    return " ".join(tokens)


def title_similarity(a: str, b: str) -> float:
    """Token-sort similarity in [0, 1] (word order insensitive)."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return SequenceMatcher(None, ta, tb).ratio()


def title_match(claimed: str | None, source: str | None, threshold: float) -> MatchResult:
    if not claimed:
        return MatchResult.NOT_APPLICABLE
    if not source:
        return MatchResult.FALSE
    return MatchResult.TRUE if title_similarity(claimed, source) >= threshold else MatchResult.FALSE


def author_match(claimed: list[str] | None, source: list[str] | None) -> MatchResult:
    if not claimed:
        return MatchResult.NOT_APPLICABLE
    source_set = {normalize_surname(s) for s in (source or []) if normalize_surname(s)}
    claimed_norm = [normalize_surname(s) for s in claimed if normalize_surname(s)]
    if not claimed_norm:
        return MatchResult.NOT_APPLICABLE
    return MatchResult.TRUE if all(s in source_set for s in claimed_norm) else MatchResult.FALSE


def year_match(claimed: int | None, source_years: list[int] | None) -> MatchResult:
    if claimed is None:
        return MatchResult.NOT_APPLICABLE
    years = {y for y in (source_years or []) if y is not None}
    if not years:
        return MatchResult.FALSE
    return MatchResult.TRUE if claimed in years else MatchResult.FALSE
