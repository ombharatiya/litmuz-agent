"""Synchronous single-claim verification and the caller-supplied-source semantics
(AC-JOB-4, AC-MCP-6). Uses the shared pipeline fakes; no network, no model."""

from litmuz_core.config import Category, IdType, RetrievalMode, TrafficLight
from litmuz_core.pipeline import verify_claim
from litmuz_core.schemas import CitedId, Passage
from litmuz_core.testing import FakeMetadataClient, FakePipelineLlm, FakeRetrievalClient


def _verify(text, cited_ids=None, caller_passages=None, llm=None):
    return verify_claim(
        text,
        cited_ids=cited_ids,
        caller_passages=caller_passages,
        llm=llm or FakePipelineLlm(),
        metadata_client=FakeMetadataClient(),
        retrieval_client=FakeRetrievalClient(),
    )


def test_supported_cited_claim_is_green():
    claim = _verify(
        "TP53 loss drives proliferation in carcinoma models.",
        cited_ids=[CitedId(id_type=IdType.PMID, value="12345")],
    )
    assert claim.traffic_light is TrafficLight.GREEN
    assert claim.verdict.label.value == "supported"
    assert claim.auto_passed is True


def test_fabricated_citation_is_red_and_skips_the_judge():
    llm = FakePipelineLlm()
    claim = _verify(
        "A bold claim.", cited_ids=[CitedId(id_type=IdType.PMID, value="99999999")], llm=llm
    )
    assert claim.traffic_light is TrafficLight.RED
    assert llm.judge_calls == 0  # the deterministic pre-filter never called the judge


def test_a_caller_source_cannot_rescue_a_fabricated_citation():
    # AC-MCP-6: a plausible caller-supplied source alongside a fabricated citation stays red.
    passage = Passage(
        source_id="caller",
        text="This strongly supports the claim.",
        retrieval_mode=RetrievalMode.CALLER_SUPPLIED,
    )
    claim = _verify(
        "A bold claim.",
        cited_ids=[CitedId(id_type=IdType.PMID, value="99999999")],
        caller_passages=[passage],
    )
    assert claim.traffic_light is TrafficLight.RED


def test_a_dosing_claim_is_capped_and_routed():
    claim = _verify(
        "The recommended dose was 5 mg daily.",
        cited_ids=[CitedId(id_type=IdType.PMID, value="12345")],
    )
    assert claim.category is Category.SAFETY_CRITICAL
    assert claim.traffic_light is not TrafficLight.GREEN  # the safety cap holds
    assert claim.routed_to_review is True


def test_caller_passages_are_used_when_provided():
    passage = Passage(
        source_id="caller",
        text="TP53 loss drives proliferation in carcinoma models.",
        retrieval_mode=RetrievalMode.CALLER_SUPPLIED,
    )
    claim = _verify(
        "TP53 loss drives proliferation in carcinoma models.",
        cited_ids=[CitedId(id_type=IdType.PMID, value="12345")],
        caller_passages=[passage],
    )
    assert claim.retrieval_mode is RetrievalMode.CALLER_SUPPLIED
    assert claim.verdict.label.value == "supported"
