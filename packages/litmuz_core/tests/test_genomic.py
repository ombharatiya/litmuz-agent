"""The deterministic genomic claim checker (HAR / Zoonomia reference)."""

from litmuz_core.config import Config, JudgeLabel, RetrievalMode, VerificationMode
from litmuz_core.genomic import check_genomic_claim
from litmuz_core.pipeline import run_pipeline
from litmuz_core.testing import FakeMetadataClient, FakePipelineLlm, FakeRetrievalClient


def test_named_har_with_a_true_assertion_is_supported():
    r = check_genomic_claim(
        "HAR1 is a Human Accelerated Region expressed during cortical development."
    )
    assert r.label is JudgeLabel.SUPPORTED
    assert r.matched == "HAR1"
    assert r.evidence.evidence_sentence is not None
    assert "16915236" in r.evidence.evidence_sentence  # cites Pollard 2006


def test_named_har_denied_is_contradicted():
    r = check_genomic_claim(
        "The HACNS1 enhancer shows no human-specific changes and is identical across primates."
    )
    assert r.label is JudgeLabel.CONTRADICTED
    assert r.matched == "HACNS1"
    assert r.evidence.evidence_sentence is not None


def test_alias_is_resolved():
    # HAR2 and CE114 are aliases of HACNS1.
    assert check_genomic_claim("HAR2 is human accelerated.").matched == "HACNS1"


def test_coordinate_without_a_known_har_is_unverifiable_not_refuted():
    r = check_genomic_claim(
        "The region chr7:250,000-251,000 is a well-characterized Human Accelerated Region."
    )
    # Honest negative: absence from the curated reference is 'cannot confirm', never a pass.
    assert r.label is None
    assert r.evidence.evidence_not_located is True
    assert r.retrieval_mode is RetrievalMode.NONE


def test_no_genomic_entity_is_unverifiable():
    r = check_genomic_claim("Aspirin reduces inflammation in most adults.")
    assert r.label is None
    assert r.evidence.evidence_not_located is True


def test_coordinate_overlapping_a_known_har_is_supported():
    # A coordinate window inside HAR1 (chr20q13.33) resolves to it.
    r = check_genomic_claim("The interval chr20:63,895,200-63,895,900 is human accelerated.")
    assert r.label is JudgeLabel.SUPPORTED
    assert r.matched == "HAR1"


def test_genomic_pipeline_yields_green_yellow_red_deterministically():
    # Genomic mode never calls the LLM: the fake clients are required by the signature but unused,
    # so this asserts an exact, reproducible verdict split (no model variance).
    memo = (
        "HAR1 is a Human Accelerated Region that evolved rapidly in the human lineage [1].\n"
        "The region chr7:250,000-251,000 is a well-characterized Human Accelerated Region [2].\n"
        "The HACNS1 enhancer shows no human-specific changes, identical across primates [3].\n"
        "\nReferences\n1. Pollard KS. Nature. 2006. PMID: 16915236.\n"
        "2. Ghost. 2099. PMID: 99999999.\n3. Test T. 2020. PMID: 34567890."
    )
    report = run_pipeline(
        memo,
        llm=FakePipelineLlm(),
        metadata_client=FakeMetadataClient(),
        retrieval_client=FakeRetrievalClient(),
        config=Config(),
        mode=VerificationMode.GENOMIC,
    )
    lights = [c.traffic_light.value for c in report.claims]
    assert lights == ["green", "yellow", "red"]
    assert report.model_versions == {"genomic_reference": "gladstone-har-zoonomia"}
    # HAR1 is grounded, HACNS1 is contradicted (a real HAR the claim denies), chr7 is unverifiable.
    assert report.claims[0].verdict.label is JudgeLabel.SUPPORTED
    assert report.claims[2].verdict.label is JudgeLabel.CONTRADICTED
    assert report.claims[1].verdict is None
