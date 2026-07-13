"""Claim decomposition (FR-1). Phase 1 ships the deterministic reference resolution;
atomic-claim extraction (LLM) lands in Phase 2."""

from .decomposer import DecomposeError, DecomposeResult, decompose
from .references import (
    ReferenceEntry,
    ReferenceIndex,
    ResolvedCitation,
    build_reference_index,
    resolve_citations,
    split_reference_section,
)

__all__ = [
    "DecomposeError",
    "DecomposeResult",
    "ReferenceEntry",
    "ReferenceIndex",
    "ResolvedCitation",
    "build_reference_index",
    "decompose",
    "resolve_citations",
    "split_reference_section",
]
