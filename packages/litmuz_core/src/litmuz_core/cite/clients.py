"""Metadata resolver clients and the client contract.

The checker depends only on the ``MetadataClient`` Protocol, so unit tests inject an
in-memory fake and never touch the network (AC-CITE unit tests). ``NcbiCrossrefClient``
is the real implementation (integration-tested later): PubMed E-utilities for PMIDs,
the NCBI ID Converter for DOI/PMCID, and Crossref as the DOI fallback (decision D6/D7).
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from ..config import Config, IdType, SourceStatus
from ..schemas import CitedId


class ResolutionOutcome(str, Enum):
    FOUND = "found"
    ABSENT = "absent"  # authoritative absence -> fabricated
    UNRESOLVED = "unresolved"  # valid-looking id not located in queried sources


@dataclass(frozen=True)
class SourceRecord:
    identifier: str
    title: str | None = None
    surnames: tuple[str, ...] = ()
    epub_year: int | None = None
    print_year: int | None = None
    source_status: SourceStatus = SourceStatus.ACTIVE
    pmid: str | None = None
    doi: str | None = None
    pmcid: str | None = None

    @property
    def years(self) -> list[int]:
        return [y for y in (self.epub_year, self.print_year) if y is not None]


@dataclass(frozen=True)
class Resolution:
    outcome: ResolutionOutcome
    record: SourceRecord | None = None
    resolver_path: str = ""


class TransientError(Exception):
    """Raised after bounded backoff; the checker maps this to ResolutionStatus.UNKNOWN."""


class MetadataClient(Protocol):
    def resolve(self, cited_id: CitedId) -> Resolution: ...


# --------------------------------------------------------------------------- #
# Real client (integration-tested, not exercised by the Phase-1 unit suite).
# --------------------------------------------------------------------------- #

_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
_IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
_CROSSREF = "https://api.crossref.org/works/"
_RETRACTED_PUBTYPES = {"retracted publication"}
_CONCERN_PUBTYPES = {"expression of concern"}


def _year(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"(19|20)\d{2}", value)
    return int(m.group(0)) if m else None


def _surname(name: str) -> str:
    parts = name.strip().split()
    return " ".join(parts[:-1]) if len(parts) > 1 else name.strip()


@dataclass
class NcbiCrossrefClient:
    config: Config
    client: object = None  # httpx.Client; created lazily to keep import light
    _retries: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if self.client is None:
            import httpx

            self.client = httpx.Client(timeout=15.0, headers={"User-Agent": "litmuz/0.0"})
        self._retries = self.config.retrieval_max_retries

    def resolve(self, cited_id: CitedId) -> Resolution:
        if cited_id.id_type is IdType.PMID:
            return self._resolve_pmid(cited_id.value)
        if cited_id.id_type is IdType.PMCID:
            return self._resolve_via_idconv(cited_id.value, "pmcid")
        return self._resolve_doi(cited_id.value)

    # -- HTTP with bounded backoff -> TransientError -------------------------- #
    def _get_json(self, url: str, params: dict) -> dict:
        if self.config.ncbi_api_key and "ncbi.nlm.nih.gov" in url:
            params = {**params, "api_key": self.config.ncbi_api_key}
        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                resp = self.client.get(url, params=params)  # type: ignore[attr-defined]
                if resp.status_code == 404:
                    return {"__status__": 404}
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise _Retryable(resp.status_code)
                resp.raise_for_status()
                return resp.json()
            except _Retryable as exc:
                last = exc
            except Exception as exc:  # network/timeout
                last = exc
            time.sleep(self.config.retrieval_base_delay_s * (2**attempt) + random.random() * 0.1)
        raise TransientError(str(last))

    def _resolve_pmid(self, pmid: str) -> Resolution:
        data = self._get_json(_ESUMMARY, {"db": "pubmed", "id": pmid, "retmode": "json"})
        result = data.get("result", {})
        entry = result.get(pmid)
        if not entry or "error" in entry:
            return Resolution(ResolutionOutcome.ABSENT, resolver_path="esummary")
        pubtypes = {p.lower() for p in entry.get("pubtype", [])}
        status = SourceStatus.ACTIVE
        if pubtypes & _RETRACTED_PUBTYPES:
            status = SourceStatus.RETRACTED
        elif pubtypes & _CONCERN_PUBTYPES:
            status = SourceStatus.CONCERN
        record = SourceRecord(
            identifier=f"pmid:{pmid}",
            title=entry.get("title"),
            surnames=tuple(_surname(a.get("name", "")) for a in entry.get("authors", [])),
            epub_year=_year(entry.get("epubdate")),
            print_year=_year(entry.get("pubdate") or entry.get("sortpubdate")),
            source_status=status,
            pmid=pmid,
        )
        return Resolution(ResolutionOutcome.FOUND, record, resolver_path="esummary")

    def _resolve_via_idconv(self, value: str, kind: str) -> Resolution:
        data = self._get_json(_IDCONV, {"ids": value, "format": "json"})
        records = data.get("records", [])
        if records and records[0].get("pmid"):
            res = self._resolve_pmid(records[0]["pmid"])
            return Resolution(res.outcome, res.record, resolver_path="idconv+esummary")
        if kind == "doi":
            return self._resolve_crossref(value)
        return Resolution(ResolutionOutcome.UNRESOLVED, resolver_path="idconv")

    def _resolve_doi(self, doi: str) -> Resolution:
        return self._resolve_via_idconv(doi, "doi")

    def _resolve_crossref(self, doi: str) -> Resolution:
        data = self._get_json(_CROSSREF + doi, {})
        if data.get("__status__") == 404:
            return Resolution(ResolutionOutcome.ABSENT, resolver_path="crossref")
        msg = data.get("message")
        if not msg:
            return Resolution(ResolutionOutcome.UNRESOLVED, resolver_path="crossref")
        title = (msg.get("title") or [None])[0]
        years = (msg.get("issued", {}).get("date-parts") or [[None]])[0]
        return Resolution(
            ResolutionOutcome.FOUND,
            SourceRecord(
                identifier=f"doi:{doi}",
                title=title,
                surnames=tuple(a.get("family", "") for a in msg.get("author", [])),
                print_year=years[0] if years else None,
                doi=doi,
            ),
            resolver_path="crossref",
        )


class _Retryable(Exception):
    pass
