"""Evidence retrieval clients and the retrieval client contract.

The retriever depends only on the ``RetrievalClient`` Protocol, so unit tests inject an
in-memory fake and never touch the network. ``NcbiPmcClient`` is the real implementation
(integration-tested later): PubMed E-utilities for cited abstracts, PMC (BioC) for
open-access full text, and E-utilities esearch for the uncited retrieval path. It mirrors
the citation layer's ``NcbiCrossrefClient``: the module imports with no HTTP SDK installed,
and httpx is only touched at construction time.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from typing import Protocol

from ..config import Config, RetrievalMode
from ..schemas import CitedId, Passage


@dataclass(frozen=True)
class CitedSource:
    """The text of a cited source plus whether open-access full text was available."""

    source_id: str
    text: str
    is_open_access_fulltext: bool  # True -> full text available, False -> abstract only


class RetrievalTransient(Exception):
    """Transient upstream failure. The retriever retries this, then raises RetrievalError.

    A transient failure is distinct from a not-found result (which the client signals by
    returning None / an empty list): truth is undetermined, not authoritatively absent.
    """


class RetrievalClient(Protocol):
    def fetch_cited(self, cited_id: CitedId) -> CitedSource | None: ...  # None -> not found

    def search(self, query: str, k: int) -> list[Passage]: ...  # ranked candidate passages


# --------------------------------------------------------------------------- #
# Real client (integration-tested, not exercised by the Phase-1 unit suite).
# --------------------------------------------------------------------------- #

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
_BIOC = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/"

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_ABSTRACT_RE = re.compile(r"<AbstractText[^>]*>(.*?)</AbstractText>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(fragment: str) -> str:
    return _TAG_RE.sub("", fragment).strip()


@dataclass
class NcbiPmcClient:
    config: Config
    client: object = None  # httpx.Client; created lazily to keep import light
    _retries: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if self.client is None:
            import httpx

            self.client = httpx.Client(timeout=30.0, headers={"User-Agent": "litmuz/0.0"})
        self._retries = max(1, self.config.retrieval_max_retries)

    def fetch_cited(self, cited_id: CitedId) -> CitedSource | None:
        pmid, pmcid = self._identifiers(cited_id)
        if pmcid:
            fulltext = self._fetch_fulltext(pmcid)
            if fulltext:
                return CitedSource(
                    source_id=f"pmcid:{pmcid}", text=fulltext, is_open_access_fulltext=True
                )
        if pmid:
            abstract = self._fetch_abstract(pmid)
            if abstract:
                return CitedSource(
                    source_id=f"pmid:{pmid}", text=abstract, is_open_access_fulltext=False
                )
        return None

    def search(self, query: str, k: int) -> list[Passage]:
        data = self._get_json(
            _ESEARCH,
            {"db": "pubmed", "term": query, "retmax": k, "retmode": "json", "sort": "relevance"},
        )
        ids = data.get("esearchresult", {}).get("idlist", [])
        passages: list[Passage] = []
        for pmid in ids[:k]:
            abstract = self._fetch_abstract(pmid)
            if abstract:
                passages.append(
                    Passage(
                        source_id=f"pmid:{pmid}",
                        text=abstract,
                        retrieval_mode=RetrievalMode.RETRIEVED,
                    )
                )
        return passages  # ranked: esearch relevance order is preserved

    # -- id resolution -------------------------------------------------------- #
    def _identifiers(self, cited_id: CitedId) -> tuple[str | None, str | None]:
        value = cited_id.value
        if cited_id.id_type.value == "pmid":
            return value, self._to_pmcid(value)
        if cited_id.id_type.value == "pmcid":
            return None, value
        record = self._idconv(value)  # doi
        return record.get("pmid"), record.get("pmcid")

    def _to_pmcid(self, pmid: str) -> str | None:
        return self._idconv(pmid).get("pmcid")

    def _idconv(self, value: str) -> dict:
        data = self._get_json(_IDCONV, {"ids": value, "format": "json"})
        records = data.get("records", [])
        return records[0] if records else {}

    # -- content fetch -------------------------------------------------------- #
    def _fetch_fulltext(self, pmcid: str) -> str | None:
        data = self._get_json(f"{_BIOC}{pmcid}/unicode", {})
        if isinstance(data, dict) and data.get("__status__") == 404:
            return None
        documents = data if isinstance(data, list) else [data]
        parts: list[str] = []
        for document in documents:
            for passage in document.get("documents", [{}])[0].get("passages", []):
                text = passage.get("text")
                if text:
                    parts.append(text)
        joined = "\n\n".join(parts).strip()
        return joined or None

    def _fetch_abstract(self, pmid: str) -> str | None:
        raw = self._get_text(
            _EFETCH, {"db": "pubmed", "id": pmid, "rettype": "abstract", "retmode": "xml"}
        )
        fragments = [_strip_tags(m) for m in _ABSTRACT_RE.findall(raw)]
        joined = "\n\n".join(f for f in fragments if f).strip()
        return joined or None

    # -- HTTP with bounded backoff -> RetrievalTransient ---------------------- #
    def _request(self, url: str, params: dict) -> object:
        if self.config.ncbi_api_key and "ncbi.nlm.nih.gov" in url:
            params = {**params, "api_key": self.config.ncbi_api_key}
        last: Exception | None = None
        for attempt in range(self._retries):
            try:
                resp = self.client.get(url, params=params)  # type: ignore[attr-defined]
                if resp.status_code == 404:
                    return resp
                if resp.status_code in _RETRYABLE_STATUS:
                    raise _Retryable(resp.status_code)
                resp.raise_for_status()
                return resp
            except _Retryable as exc:
                last = exc
            except Exception as exc:  # network/timeout
                last = exc
            time.sleep(self.config.retrieval_base_delay_s * (2**attempt) + random.random() * 0.1)
        raise RetrievalTransient(str(last))

    def _get_json(self, url: str, params: dict) -> object:
        resp = self._request(url, params)
        if resp.status_code == 404:  # type: ignore[attr-defined]
            return {"__status__": 404}
        return resp.json()  # type: ignore[attr-defined]

    def _get_text(self, url: str, params: dict) -> str:
        resp = self._request(url, params)
        if resp.status_code == 404:  # type: ignore[attr-defined]
            return ""
        return resp.text  # type: ignore[attr-defined]


class _Retryable(Exception):
    pass
