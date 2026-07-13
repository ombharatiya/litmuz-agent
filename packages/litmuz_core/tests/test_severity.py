"""AC-SEVERITY-1..5, AC-CITE-9, AC-SAFETY-1..4, AC-ROUTING-1 for the severity stage.

Everything here is offline: the mapping is a pure function, so the tests construct
CitationCheck values by hand and assert the exact diagnostic, traffic light and routing
flags. The exhaustive table is the core of AC-SEVERITY-1; the pass line is an exact match
on every row.
"""

from dataclasses import FrozenInstanceError

import pytest

from litmuz_core.config import (
    Category,
    Diagnostic,
    IdType,
    JudgeLabel,
    ResolutionStatus,
    RetrievalMode,
    SourceStatus,
    TrafficLight,
)
from litmuz_core.schemas import CitationCheck
from litmuz_core.severity import SeverityResult, score_claim

# Short aliases keep the fixture table readable and inside the line-length limit.
S = JudgeLabel.SUPPORTED
C = JudgeLabel.CONTRADICTED
U = JudgeLabel.UNSUPPORTED
JE = JudgeLabel.JUDGE_ERROR

OK = ResolutionStatus.OK
MM = ResolutionStatus.METADATA_MISMATCH
FAB = ResolutionStatus.FABRICATED
UNK = ResolutionStatus.UNKNOWN
UNR = ResolutionStatus.UNRESOLVED

ACT = SourceStatus.ACTIVE
RET = SourceStatus.RETRACTED
CON = SourceStatus.CONCERN

FT = RetrievalMode.CITED_FULLTEXT
AB = RetrievalMode.CITED_ABSTRACT
RTV = RetrievalMode.RETRIEVED
NON = RetrievalMode.NONE

MECH = Category.MECHANISTIC
CIT = Category.CITATION
SAFE = Category.SAFETY_CRITICAL

D1 = Diagnostic.D1
D2 = Diagnostic.D2
D3 = Diagnostic.D3
D4 = Diagnostic.D4
D5 = Diagnostic.D5

GREEN = TrafficLight.GREEN
YELLOW = TrafficLight.YELLOW
RED = TrafficLight.RED

# A lexically neutral claim so only an explicit safety_critical category trips the guard.
NEUTRAL = "The protein was expressed in cultured cells."


def _check(resolution: ResolutionStatus, source: SourceStatus | None = ACT) -> CitationCheck:
    """Build one CitationCheck with the given resolution and source posture."""
    return CitationCheck(
        identifier="pmid:1",
        id_type=IdType.PMID,
        resolution_status=resolution,
        source_status=source,
    )


# Rows: (label, confidence, cited_status, source_status, retrieval_mode, category,
#        expected_diagnostic, expected_traffic_light). label None means the claim never
# reached the judge. See AC-SEVERITY-2 for the branch order these rows exercise.
TABLE = [
    # D1: grounded, high confidence, clean citation, full evidence.
    (S, 0.95, OK, ACT, FT, MECH, D1, GREEN),
    (S, 0.95, OK, ACT, RTV, CIT, D1, GREEN),
    # D2: supported with a gap. Green only when confidence clears the borderline knob.
    (S, 0.80, OK, ACT, FT, MECH, D2, GREEN),
    (S, 0.60, OK, ACT, FT, MECH, D2, YELLOW),
    (S, None, OK, ACT, FT, MECH, D2, YELLOW),
    (S, 0.95, MM, ACT, FT, CIT, D2, GREEN),
    (S, 0.95, OK, ACT, AB, MECH, D2, GREEN),
    (S, 0.80, MM, ACT, AB, CIT, D2, GREEN),
    (S, 0.60, MM, ACT, RTV, MECH, D2, YELLOW),
    (S, 0.80, OK, ACT, RTV, MECH, D2, GREEN),
    (S, 0.60, OK, ACT, RTV, CIT, D2, YELLOW),
    (S, None, MM, ACT, RTV, MECH, D2, YELLOW),
    (S, None, OK, ACT, AB, CIT, D2, YELLOW),
    # D3: unverifiable. Retrieval produced nothing, the citation is undetermined, or the
    # judge did not return a usable label.
    (S, 0.95, UNK, ACT, RTV, MECH, D3, YELLOW),
    (S, 0.95, UNR, ACT, RTV, CIT, D3, YELLOW),
    (U, 0.95, OK, ACT, NON, MECH, D3, YELLOW),
    (JE, 0.80, OK, ACT, RTV, MECH, D3, YELLOW),
    (JE, None, OK, ACT, NON, CIT, D3, YELLOW),
    (None, None, OK, ACT, RTV, MECH, D3, YELLOW),
    (None, None, OK, ACT, NON, CIT, D3, YELLOW),
    (C, 0.95, OK, ACT, NON, MECH, D3, YELLOW),
    # D4: unsupported with evidence available.
    (U, 0.95, OK, ACT, RTV, MECH, D4, YELLOW),
    (U, 0.60, OK, ACT, FT, CIT, D4, YELLOW),
    (U, 0.95, MM, ACT, RTV, MECH, D4, YELLOW),
    (U, None, OK, ACT, AB, CIT, D4, YELLOW),
    # D5: contradicted, or fabricated citation forcing red regardless of the label.
    (C, 0.95, OK, ACT, RTV, MECH, D5, RED),
    (C, 0.60, OK, ACT, FT, CIT, D5, RED),
    (C, None, OK, ACT, AB, MECH, D5, RED),
    (S, 0.95, FAB, ACT, FT, MECH, D5, RED),
    (U, 0.60, FAB, ACT, RTV, CIT, D5, RED),
    (JE, None, FAB, ACT, NON, MECH, D5, RED),
    (C, 0.95, FAB, ACT, RTV, CIT, D5, RED),
    (None, None, FAB, ACT, NON, MECH, D5, RED),
    # AC-CITE-9: a retracted source or expression of concern caps green to yellow.
    (S, 0.95, OK, RET, FT, MECH, D2, YELLOW),
    (S, 0.80, MM, RET, FT, CIT, D2, YELLOW),
    (S, 0.95, OK, CON, RTV, MECH, D2, YELLOW),
    (C, 0.95, OK, RET, RTV, CIT, D5, RED),
    (U, 0.95, OK, RET, RTV, MECH, D4, YELLOW),
    # safety_critical category downgrades green to yellow but leaves the diagnostic.
    (S, 0.95, OK, ACT, FT, SAFE, D1, YELLOW),
    (S, 0.80, OK, ACT, FT, SAFE, D2, YELLOW),
    (C, 0.95, OK, ACT, RTV, SAFE, D5, RED),
    (S, 0.60, OK, ACT, FT, SAFE, D2, YELLOW),
]


@pytest.mark.parametrize(
    "label,confidence,cited,source,retrieval,category,exp_diag,exp_light",
    TABLE,
)
def test_severity_table(
    label, confidence, cited, source, retrieval, category, exp_diag, exp_light, config
):
    # AC-SEVERITY-1: 100% exact match on (diagnostic, traffic_light) for every row.
    result = score_claim(
        category=category,
        label=label,
        confidence=confidence,
        citation_checks=[_check(cited, source)],
        retrieval_mode=retrieval,
        claim_text=NEUTRAL,
        config=config,
    )
    assert result.diagnostic == exp_diag
    assert result.traffic_light == exp_light


def test_result_is_frozen_dataclass(config):
    result = score_claim(
        category=MECH,
        label=S,
        confidence=0.95,
        citation_checks=[],
        retrieval_mode=FT,
        claim_text=NEUTRAL,
        config=config,
    )
    assert isinstance(result, SeverityResult)
    with pytest.raises(FrozenInstanceError):
        result.diagnostic = D5  # frozen: assignment must fail


def test_safety_critical_adversarial_never_auto_passes(config):
    # AC-SAFETY-2: a perfect supported verdict on a safety-critical claim is still blocked.
    result = score_claim(
        category=SAFE,
        label=S,
        confidence=1.0,
        citation_checks=[_check(OK, ACT)],
        retrieval_mode=FT,
        claim_text=NEUTRAL,
        config=config,
    )
    assert result.traffic_light != GREEN
    assert result.auto_pass_blocked is True
    assert result.auto_passed is False
    assert result.routed_to_review is True


def test_lexical_guard_independent_of_category(config):
    # AC-SAFETY-4: the model labelled this mechanistic, but the lexical oracle sees a dose.
    result = score_claim(
        category=MECH,
        label=S,
        confidence=0.95,
        citation_checks=[_check(OK, ACT)],
        retrieval_mode=FT,
        claim_text="The recommended dose was 5 mg daily.",
        config=config,
    )
    assert result.diagnostic == D1  # the branch alone would grade it grounded
    assert result.traffic_light != GREEN
    assert result.traffic_light == YELLOW
    assert result.auto_pass_blocked is True
    assert result.auto_passed is False


def test_multi_citation_worst_case_aggregation(config):
    # AC-SEVERITY-5: one clean citation and one fabricated one aggregates to fabricated.
    result = score_claim(
        category=MECH,
        label=S,
        confidence=0.95,
        citation_checks=[_check(OK, ACT), _check(FAB, None)],
        retrieval_mode=FT,
        claim_text=NEUTRAL,
        config=config,
    )
    assert result.diagnostic == D5
    assert result.traffic_light == RED


def test_routing_non_judged_claim_is_routed(config):
    # AC-ROUTING-1: a claim that never reached the judge (confidence None) routes.
    result = score_claim(
        category=MECH,
        label=None,
        confidence=None,
        citation_checks=[],
        retrieval_mode=NON,
        claim_text=NEUTRAL,
        config=config,
    )
    assert result.diagnostic == D3
    assert result.routed_to_review is True
    assert result.auto_passed is False


def test_routing_clean_green_claim_auto_passes(config):
    # AC-ROUTING-1: a clean, high-confidence, non-safety green claim auto-passes.
    result = score_claim(
        category=MECH,
        label=S,
        confidence=0.95,
        citation_checks=[],
        retrieval_mode=FT,
        claim_text=NEUTRAL,
        config=config,
    )
    assert result.diagnostic == D1
    assert result.traffic_light == GREEN
    assert result.auto_pass_blocked is False
    assert result.routed_to_review is False
    assert result.auto_passed is True


def test_below_calibration_threshold_green_still_routes(config):
    # AC-ROUTING-1: a green claim under the calibration threshold routes but is not blocked.
    result = score_claim(
        category=MECH,
        label=S,
        confidence=0.72,
        citation_checks=[],
        retrieval_mode=RTV,
        claim_text=NEUTRAL,
        config=config,
    )
    assert result.traffic_light == GREEN
    assert result.auto_pass_blocked is False
    assert result.routed_to_review is True
    assert result.auto_passed is False
