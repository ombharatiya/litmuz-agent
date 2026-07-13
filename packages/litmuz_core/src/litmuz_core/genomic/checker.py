"""Deterministic genomic claim checking against the curated HAR / Zoonomia reference.

This is the genomic-mode analogue of the deterministic citation checker: no LLM and no network.
Given a claim's text, it recognizes any human accelerated region named in it (HAR1, HACNS1, ...)
or a genomic coordinate, decides whether the claim's assertion agrees with the reference, and
returns a verdict the shared severity mapping turns into a traffic light. Absence from the curated
reference is an honest "cannot confirm" (unverifiable), never a silent pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import JudgeLabel, RetrievalMode
from ..schemas import Evidence
from .reference import ZOONOMIA_NOTE, GenomicElement, find_by_coordinate, find_by_name

# A claim that DENIES human acceleration / human-specific change (so it contradicts a real HAR).
_NEGATION = re.compile(
    r"\b(no human[- ]specific|not (a )?human[- ]accelerated|not accelerated|no acceleration|"
    r"identical (across|in|to|among)|unchanged in humans|shows no|without human[- ]specific|"
    r"not rapidly (evolved|evolving)|conserved and unchanged|no rapid)\b",
    re.IGNORECASE,
)

# A claim that ASSERTS HAR / accelerated / conservation status (the common case).
_HAR_ASSERTION = re.compile(
    r"\b(human[- ]accelerated region|\bHAR\b|accelerated|rapidly evolv|human[- ]specific|"
    r"conserved|purifying selection|constraint)\b",
    re.IGNORECASE,
)

_COORD = re.compile(r"\b(chr[\dXYM]+)\s*:\s*([\d,]+)\s*[-–]\s*([\d,]+)", re.IGNORECASE)


@dataclass(frozen=True)
class GenomicResult:
    """The genomic-check output for one claim, shaped to feed the severity mapping."""

    label: JudgeLabel | None
    confidence: float | None
    rationale: str
    evidence: Evidence
    retrieval_mode: RetrievalMode
    matched: str | None


def _supported(el: GenomicElement, where: str) -> GenomicResult:
    sentence = (
        f"{el.name} ({el.locus}) is a confirmed human accelerated region: {el.description}. "
        f"Source: {el.citation}."
    )
    return GenomicResult(
        label=JudgeLabel.SUPPORTED,
        confidence=0.95,
        rationale=f"{where} matches {el.name}, a documented human accelerated region.",
        evidence=Evidence(evidence_sentence=sentence, source_locator={"element": el.name}),
        retrieval_mode=RetrievalMode.RETRIEVED,
        matched=el.name,
    )


def _contradicted(el: GenomicElement) -> GenomicResult:
    sentence = (
        f"{el.name} ({el.locus}) is a confirmed human accelerated region ({el.description}); "
        f"the claim that it is unchanged or shows no human-specific change is contradicted by the "
        f"reference. Source: {el.citation}."
    )
    return GenomicResult(
        label=JudgeLabel.CONTRADICTED,
        confidence=0.9,
        rationale=(
            f"The reference records {el.name} as strongly human-accelerated, which contradicts "
            f"the claim."
        ),
        evidence=Evidence(evidence_sentence=sentence, source_locator={"element": el.name}),
        retrieval_mode=RetrievalMode.RETRIEVED,
        matched=el.name,
    )


def _unverifiable(reason: str) -> GenomicResult:
    return GenomicResult(
        label=None,
        confidence=None,
        rationale=reason,
        evidence=Evidence(evidence_not_located=True),
        retrieval_mode=RetrievalMode.NONE,
        matched=None,
    )


def check_genomic_claim(claim_text: str) -> GenomicResult:
    """Resolve one claim against the HAR / Zoonomia reference. Deterministic, no side effects."""
    negated = bool(_NEGATION.search(claim_text))

    # 1) A named element is the strongest signal: we know its truth from the reference.
    element = find_by_name(claim_text)
    if element is not None:
        if negated:
            return _contradicted(element)
        return _supported(element, element.name)

    # 2) A coordinate: confirm only if it overlaps a known HAR; otherwise be honest.
    coord = _COORD.search(claim_text)
    if coord is not None:
        chrom = coord.group(1)
        start = int(coord.group(2).replace(",", ""))
        end = int(coord.group(3).replace(",", ""))
        overlap = find_by_coordinate(chrom, start, end)
        if overlap is not None:
            return _supported(overlap, f"{chrom}:{start:,}-{end:,}")
        if _HAR_ASSERTION.search(claim_text):
            return _unverifiable(
                f"No human accelerated region in the curated reference overlaps "
                f"{chrom}:{start:,}-{end:,}; the claim cannot be confirmed from the loaded data. "
                f"{ZOONOMIA_NOTE}."
            )
        return _unverifiable(
            f"{chrom}:{start:,}-{end:,} was recognized but the claim makes no checkable "
            f"conservation or acceleration assertion."
        )

    # 3) Nothing to check against the genomic reference.
    return _unverifiable(
        "No human accelerated region, genomic coordinate, or recognized element was found in this "
        "claim, so it cannot be verified against the genomic reference."
    )
