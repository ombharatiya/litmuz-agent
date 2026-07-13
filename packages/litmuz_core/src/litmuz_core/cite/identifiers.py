"""Parse and normalize PMID / DOI / PMCID identifiers. Pure string work, no I/O."""

from __future__ import annotations

import re

from ..config import IdType
from ..schemas import CitedId

# A DOI: 10.<registrant>/<suffix>. Suffix runs to whitespace or a closing bracket.
_DOI_CORE = r"10\.\d{4,9}/[^\s\"<>)\]}]+"

_RE_PMID = re.compile(r"\bPMID\s*[:#]?\s*(\d{1,9})\b", re.IGNORECASE)
_RE_PMCID = re.compile(r"\bPMC\s*[:#]?\s*(\d{1,9})\b", re.IGNORECASE)
_RE_DOI_LABELLED = re.compile(
    rf"\b(?:DOI\s*[:#]?\s*|https?://(?:dx\.)?doi\.org/)({_DOI_CORE})", re.IGNORECASE
)
_RE_DOI_BARE = re.compile(rf"(?<![/\w])({_DOI_CORE})", re.IGNORECASE)

# Trailing punctuation that commonly clings to a DOI in prose but is not part of it.
_DOI_TRAILING = ".,;:)]}>\"'"


def normalize_pmid(raw: str) -> str:
    return raw.strip().lstrip("0") or "0"


def normalize_pmcid(raw: str) -> str:
    digits = re.sub(r"(?i)^pmc", "", raw.strip())
    return "PMC" + digits.lstrip("0").rjust(1, "0")


def normalize_doi(raw: str) -> str:
    doi = raw.strip()
    doi = re.sub(r"(?i)^https?://(?:dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"(?i)^doi\s*[:#]?\s*", "", doi)
    doi = doi.rstrip(_DOI_TRAILING)
    return doi.lower()


def extract_identifiers(text: str) -> list[CitedId]:
    """Extract inline PMID/DOI/PMCID identifiers from a text span (AC-DECOMP-3).

    Deduplicated, order-preserving. Labelled DOIs and PMIDs/PMCIDs are matched
    first; bare DOIs are then swept up if not already captured.
    """
    found: list[CitedId] = []
    seen: set[tuple[IdType, str]] = set()

    def add(id_type: IdType, value: str) -> None:
        key = (id_type, value)
        if value and key not in seen:
            seen.add(key)
            found.append(CitedId(id_type=id_type, value=value))

    for m in _RE_PMID.finditer(text):
        add(IdType.PMID, normalize_pmid(m.group(1)))
    for m in _RE_PMCID.finditer(text):
        add(IdType.PMCID, normalize_pmcid("PMC" + m.group(1)))
    for m in _RE_DOI_LABELLED.finditer(text):
        add(IdType.DOI, normalize_doi(m.group(1)))
    for m in _RE_DOI_BARE.finditer(text):
        add(IdType.DOI, normalize_doi(m.group(1)))

    return found
