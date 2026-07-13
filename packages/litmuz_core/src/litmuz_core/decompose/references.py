"""Deterministic citation extraction and reference resolution (AC-DECOMP-3/7).

Real agent memos rarely inline raw PMIDs; they cite with numbered markers ``[1]`` or
author-year ``(Smith et al., 2020)`` backed by a reference list. This module is pure
string work (no LLM): it builds a reference index from the bibliography and resolves a
claim's in-text markers, plus any inline identifiers, to concrete identifiers, each
paired with the attribution (surnames, year) needed by the citation check.

Title attribution is intentionally left unset here: freeform reference titles cannot be
parsed reliably, and a wrong parse would fabricate a metadata mismatch. Author and year
are the reliable deterministic signals; the title rule still applies when a title is
supplied (e.g. a caller-supplied source).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..cite.identifiers import extract_identifiers
from ..cite.matching import normalize_surname
from ..schemas import CitedId, ClaimAttribution

# Character classes that must match real-world typography without embedding literal
# typographic glyphs in this source file: straight and curly apostrophes in author names,
# and en dashes in numeric ranges.
_APOS = "'" + chr(0x2019)
_NDASH = chr(0x2013)

_RE_HEADING = re.compile(r"(?im)^\s*#*\s*(references|bibliography|works cited)\s*:?\s*$")
_RE_NUMBERED_ENTRY = re.compile(r"(?m)^\s*\[?(\d{1,3})\]?[.)]\s+")
_RE_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_RE_AUTHOR = re.compile(r"([A-Z][A-Za-z" + _APOS + r"\-]+)\s+(?:[A-Z]\.?){1,3}(?=[,;.\s]|$)")

# In-text markers.
_RE_NUM_MARKER = re.compile(r"\[(\d{1,3}(?:\s*[-" + _NDASH + r",]\s*\d{1,3})*)\]")
_RE_PAREN = re.compile(r"\(([^)]*(?:19|20)\d{2}[a-z]?[^)]*)\)")
_RE_AY_CHUNK = re.compile(r"([A-Z][A-Za-z" + _APOS + r"\-]+).*?((?:19|20)\d{2})")


@dataclass
class ReferenceEntry:
    key: str
    raw: str
    cited_ids: list[CitedId]
    attribution: ClaimAttribution


@dataclass
class ReferenceIndex:
    numbered: dict[str, ReferenceEntry] = field(default_factory=dict)
    by_author_year: dict[tuple[str, int], ReferenceEntry] = field(default_factory=dict)


@dataclass
class ResolvedCitation:
    cited_id: CitedId
    attribution: ClaimAttribution


def split_reference_section(memo: str) -> tuple[str, str]:
    """Return (body, reference_text). Reference text is empty if no heading is found."""
    match = _RE_HEADING.search(memo)
    if not match:
        return memo, ""
    return memo[: match.start()], memo[match.end() :]


def _entry_attribution(raw: str) -> ClaimAttribution:
    head = raw[:400]
    surnames: list[str] = []
    for m in _RE_AUTHOR.finditer(head):
        surnames.append(m.group(1))
        if len(surnames) >= 12:
            break
    year_m = _RE_YEAR.search(raw)
    year = int(year_m.group(0)) if year_m else None
    return ClaimAttribution(surnames=surnames, year=year)


def _make_entry(key: str, raw: str) -> ReferenceEntry:
    return ReferenceEntry(
        key=key,
        raw=raw.strip(),
        cited_ids=extract_identifiers(raw),
        attribution=_entry_attribution(raw),
    )


def build_reference_index(memo: str) -> ReferenceIndex:
    _, ref_text = split_reference_section(memo)
    index = ReferenceIndex()
    if not ref_text.strip():
        return index

    starts = list(_RE_NUMBERED_ENTRY.finditer(ref_text))
    if starts:
        for i, m in enumerate(starts):
            key = str(int(m.group(1)))
            end = starts[i + 1].start() if i + 1 < len(starts) else len(ref_text)
            entry = _make_entry(key, ref_text[m.end() : end])
            index.numbered[key] = entry
            _index_author_year(index, entry)
    else:
        for line in ref_text.splitlines():
            if not line.strip():
                continue
            _index_author_year(index, _make_entry("", line))
    return index


def _index_author_year(index: ReferenceIndex, entry: ReferenceEntry) -> None:
    attr = entry.attribution
    if attr.surnames and attr.year is not None:
        index.by_author_year[(normalize_surname(attr.surnames[0]), attr.year)] = entry


def _expand_numbered(token: str) -> list[str]:
    keys: list[str] = []
    for part in token.split(","):
        part = part.strip().replace(_NDASH, "-")
        if "-" in part:
            lo, hi = part.split("-", 1)
            if lo.strip().isdigit() and hi.strip().isdigit():
                keys.extend(str(n) for n in range(int(lo), int(hi) + 1))
        elif part.isdigit():
            keys.append(str(int(part)))
    return keys


def resolve_citations(claim_text: str, index: ReferenceIndex) -> list[ResolvedCitation]:
    """Resolve a claim's markers + inline identifiers to (identifier, attribution) pairs."""
    resolved: list[ResolvedCitation] = []
    seen: set[tuple[str, str]] = set()

    def add(cited_id: CitedId, attribution: ClaimAttribution) -> None:
        dedupe = (cited_id.id_type.value, cited_id.value)
        if dedupe not in seen:
            seen.add(dedupe)
            resolved.append(ResolvedCitation(cited_id=cited_id, attribution=attribution))

    # Numbered markers -> numbered reference entries.
    for marker in _RE_NUM_MARKER.finditer(claim_text):
        for key in _expand_numbered(marker.group(1)):
            entry = index.numbered.get(key)
            if entry:
                for cid in entry.cited_ids:
                    add(cid, entry.attribution)

    # Author-year markers -> author-year reference entries.
    for paren in _RE_PAREN.finditer(claim_text):
        for chunk in paren.group(1).split(";"):
            ay = _RE_AY_CHUNK.search(chunk)
            if not ay:
                continue
            entry = index.by_author_year.get((normalize_surname(ay.group(1)), int(ay.group(2))))
            if entry:
                for cid in entry.cited_ids:
                    add(cid, entry.attribution)

    # Inline identifiers written directly in the claim (no attribution to compare).
    for cid in extract_identifiers(claim_text):
        add(cid, ClaimAttribution())

    return resolved
