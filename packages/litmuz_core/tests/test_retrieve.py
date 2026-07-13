"""AC-RETRIEVE-1..8: the evidence retrieval stage. All offline; a FakeRetrievalClient only.

The retriever depends on the RetrievalClient Protocol, so these tests inject an in-memory
fake and never touch the network.
"""

import pytest

from litmuz_core.config import Config, IdType, RetrievalMode
from litmuz_core.retrieve import (
    CitedSource,
    RetrievalError,
    RetrievalTransient,
    retrieve_for_claim,
)
from litmuz_core.schemas import CitedId, Claim, Passage, SourceSpan


def _claim(text: str, cited: list[CitedId] | None = None) -> Claim:
    return Claim(
        id="c1",
        ordinal=0,
        text=text,
        source_span=SourceSpan(start=0, end=len(text)),
        cited_ids=cited or [],
    )


def _pmid(value: str = "12345") -> CitedId:
    return CitedId(id_type=IdType.PMID, value=value)


def _passage(source_id: str, text: str) -> Passage:
    return Passage(source_id=source_id, text=text, retrieval_mode=RetrievalMode.RETRIEVED)


class FakeRetrievalClient:
    """In-memory RetrievalClient. Configurable per test; records every call."""

    def __init__(
        self,
        cited: CitedSource | None = None,
        results: list[Passage] | None = None,
        transient: bool = False,
    ) -> None:
        self._cited = cited
        self._results = results if results is not None else []
        self._transient = transient
        self.fetch_calls = 0
        self.search_calls = 0
        self.search_k: int | None = None
        self.last_query: str | None = None

    def fetch_cited(self, cited_id: CitedId) -> CitedSource | None:
        self.fetch_calls += 1
        if self._transient:
            raise RetrievalTransient("fake transient")
        return self._cited

    def search(self, query: str, k: int) -> list[Passage]:
        self.search_calls += 1
        self.search_k = k
        self.last_query = query
        if self._transient:
            raise RetrievalTransient("fake transient")
        return list(self._results)


def test_cited_fulltext_chunks_and_keeps_a_later_supporting_sentence():
    # AC-RETRIEVE-1 and AC-RETRIEVE-8: chunk full text; a sentence in a later chunk survives.
    filler = " ".join(f"word{i}" for i in range(80))
    supporting = "TP53 induces apoptosis in response to DNA damage."
    full_text = f"{filler} {supporting} {filler}"
    source = CitedSource(source_id="pmcid:PMC1", text=full_text, is_open_access_fulltext=True)
    config = Config(max_passage_tokens=10)
    client = FakeRetrievalClient(cited=source)

    claim = _claim("does TP53 drive apoptosis?", [_pmid()])
    passages, mode = retrieve_for_claim(claim, client, config)

    assert mode is RetrievalMode.CITED_FULLTEXT
    assert len(passages) > 1  # the source was actually split into multiple chunks
    assert all(p.retrieval_mode is RetrievalMode.CITED_FULLTEXT for p in passages)
    assert all(p.source_id == "pmcid:PMC1" for p in passages)
    # Every passage is a verbatim substring of the source (no paraphrase).
    assert all(p.text in full_text for p in passages)
    # Token cap honored: at most max_passage_tokens whitespace tokens per chunk.
    assert all(len(p.text.split()) <= config.max_passage_tokens for p in passages)
    # The supporting sentence, which lives in a later chunk, is still present.
    assert any(supporting in p.text for p in passages)


def test_cited_abstract_only_is_mode_cited_abstract():
    # AC-RETRIEVE-1: abstract-only source -> CITED_ABSTRACT, verbatim.
    abstract = "Acetaminophen overdose causes dose-dependent hepatotoxicity."
    source = CitedSource(source_id="pmid:12345", text=abstract, is_open_access_fulltext=False)
    client = FakeRetrievalClient(cited=source)

    claim = _claim("is acetaminophen hepatotoxic?", [_pmid()])
    passages, mode = retrieve_for_claim(claim, client, Config())

    assert mode is RetrievalMode.CITED_ABSTRACT
    assert passages
    assert all(p.retrieval_mode is RetrievalMode.CITED_ABSTRACT for p in passages)
    assert all(p.text in abstract for p in passages)


def test_uncited_claim_returns_ranked_search_results_in_order():
    # AC-RETRIEVE-2: no citation -> search; ranked order is preserved for the caller.
    ranked = [_passage(f"pmid:{i}", f"candidate passage number {i}") for i in range(1, 6)]
    client = FakeRetrievalClient(results=ranked)
    config = Config(top_k=5)

    claim = _claim("does EGFR signaling drive proliferation?")
    passages, mode = retrieve_for_claim(claim, client, config)

    assert mode is RetrievalMode.RETRIEVED
    assert client.search_calls == 1
    assert client.search_k == config.top_k  # searched with config.top_k, not a literal
    assert [p.source_id for p in passages] == [p.source_id for p in ranked]  # order preserved
    assert [p.text for p in passages] == [p.text for p in ranked]


def test_nothing_found_returns_empty_and_none():
    # AC-RETRIEVE-3: fetch_cited None and search [] -> ([], NONE).
    client = FakeRetrievalClient(cited=None, results=[])

    claim = _claim("an unciteable claim", [_pmid("99999999")])
    passages, mode = retrieve_for_claim(claim, client, Config())

    assert passages == []
    assert mode is RetrievalMode.NONE
    assert client.fetch_calls == 1  # the citation was attempted
    assert client.search_calls == 1  # then the search fallback was attempted


def test_transient_failure_raises_retrieval_error_not_none():
    # AC-RETRIEVE-6: a transient upstream failure is retried, then raised; never NONE.
    config = Config(retrieval_max_retries=3, retrieval_base_delay_s=0.0)
    client = FakeRetrievalClient(transient=True)

    with pytest.raises(RetrievalError):
        retrieve_for_claim(_claim("some claim", [_pmid()]), client, config)

    # Bounded retries were actually exhausted, and the state is an error, not not-found.
    assert client.fetch_calls == config.retrieval_max_retries


def test_transient_on_search_path_also_raises():
    config = Config(retrieval_max_retries=2, retrieval_base_delay_s=0.0)
    client = FakeRetrievalClient(transient=True)

    with pytest.raises(RetrievalError):
        retrieve_for_claim(_claim("an uncited claim"), client, config)

    assert client.search_calls == config.retrieval_max_retries
