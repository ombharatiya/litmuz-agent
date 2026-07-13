"""AC-DECOMP-1,2,4,5,8,9,10: atomic-claim decomposition, fully offline.

The fake LlmClient returns a canned JSON array whose strings are verbatim substrings of
the memo, so span recovery and citation attachment are exercised without a model call.
"""

from __future__ import annotations

import json

import pytest

from litmuz_core.config import Config
from litmuz_core.decompose.decomposer import DecomposeError, decompose
from litmuz_core.llm import LlmResponse

TWO_SENTENCES = "Kinase X inhibits the pathway. TP53 loss drives proliferation."

CITATION_MEMO = """\
TP53 loss drives proliferation [1].

References
1. Smith J, Doe A. A TP53 study in carcinoma. Nature. 2020. PMID: 12345.
"""


class FakeLlm:
    """Returns a fixed JSON array of claim strings and records whether it was called."""

    def __init__(self, claims: list[str]) -> None:
        self._payload = json.dumps(claims)
        self.called = False

    def complete(self, *, system, prompt, temperature=0.0, max_tokens=1024) -> LlmResponse:
        self.called = True
        return LlmResponse(text=self._payload, model="fake")


@pytest.fixture
def config() -> Config:
    return Config()


def test_basic_extraction_recovers_spans_and_ordinals(config):
    claim_a = "Kinase X inhibits the pathway."
    claim_b = "TP53 loss drives proliferation."
    result = decompose(TWO_SENTENCES, FakeLlm([claim_a, claim_b]), config)

    assert len(result.claims) == 2
    first, second = result.claims
    assert first.text == claim_a
    assert TWO_SENTENCES[first.source_span.start : first.source_span.end] == claim_a
    assert first.ordinal == 0
    assert second.text == claim_b
    assert TWO_SENTENCES[second.source_span.start : second.source_span.end] == claim_b
    assert second.ordinal == 1


def test_byte_cap_rejects_before_model_call(config):
    oversized = "x" * (config.max_input_bytes + 1)
    fake = FakeLlm(["ignored"])
    with pytest.raises(DecomposeError):
        decompose(oversized, fake, config)
    assert fake.called is False


def test_empty_input_raises(config):
    with pytest.raises(DecomposeError):
        decompose("", FakeLlm([]), config)


def test_whitespace_only_input_raises(config):
    with pytest.raises(DecomposeError):
        decompose("   \n\t  ", FakeLlm([]), config)


def test_zero_claim_memo_returns_empty_result(config):
    result = decompose(TWO_SENTENCES, FakeLlm([]), config)
    assert result.claims == []


def test_duplicate_claim_text_yields_single_claim(config):
    claim = "Kinase X inhibits the pathway."
    result = decompose(TWO_SENTENCES, FakeLlm([claim, claim]), config)
    assert len(result.claims) == 1
    assert result.claims[0].text == claim


def test_citation_marker_attaches_cited_id(config):
    claim = "TP53 loss drives proliferation [1]."
    result = decompose(CITATION_MEMO, FakeLlm([claim]), config)
    assert len(result.claims) == 1
    values = [cid.value for cid in result.claims[0].cited_ids]
    assert "12345" in values


def test_unclaimed_spans_cover_the_uncovered_sentence(config):
    claimed = "Kinase X inhibits the pathway."
    uncovered = "TP53 loss drives proliferation."
    result = decompose(TWO_SENTENCES, FakeLlm([claimed]), config)

    assert any(uncovered in TWO_SENTENCES[span.start : span.end] for span in result.unclaimed_spans)
