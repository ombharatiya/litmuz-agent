"""Deterministic citation verification (FR-2). No LLM in this package."""

from .checker import ResolutionCache, check_citation, identifier_key
from .clients import (
    MetadataClient,
    NcbiCrossrefClient,
    Resolution,
    ResolutionOutcome,
    SourceRecord,
    TransientError,
)
from .identifiers import extract_identifiers, normalize_doi, normalize_pmcid, normalize_pmid

__all__ = [
    "check_citation",
    "identifier_key",
    "ResolutionCache",
    "MetadataClient",
    "NcbiCrossrefClient",
    "Resolution",
    "ResolutionOutcome",
    "SourceRecord",
    "TransientError",
    "extract_identifiers",
    "normalize_pmid",
    "normalize_doi",
    "normalize_pmcid",
]
