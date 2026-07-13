"""Deterministic severity mapping: a verdict plus its citation state become a
diagnostic, a traffic light and routing flags (AC-SEVERITY-1..5, AC-CITE-9,
AC-SAFETY-1..4, AC-ROUTING-1).

No LLM and no network. ``score_claim`` is a pure function of its inputs: given the
judge label, its confidence, the deterministic citation checks, the retrieval mode
and the claim category it returns the same result every time. Two independent gates
guard the green light. A retracted source or an expression of concern can never be
green (AC-CITE-9), and a safety-critical claim, whether the model categorized it so or
the lexical oracle did, can never be green and can never auto-pass (AC-SAFETY-1..4).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import (
    Category,
    Config,
    Diagnostic,
    JudgeLabel,
    ResolutionStatus,
    RetrievalMode,
    SourceStatus,
    TrafficLight,
)
from ..safety import is_safety_critical_text
from ..schemas import CitationCheck

# Worst-first precedence for reducing many citation resolutions to one status.
_CITED_PRECEDENCE: tuple[ResolutionStatus, ...] = (
    ResolutionStatus.FABRICATED,
    ResolutionStatus.METADATA_MISMATCH,
    ResolutionStatus.UNKNOWN,
    ResolutionStatus.UNRESOLVED,
    ResolutionStatus.OK,
)

# Worst-first precedence for reducing many source postures to one status.
_SOURCE_PRECEDENCE: tuple[SourceStatus, ...] = (
    SourceStatus.RETRACTED,
    SourceStatus.CONCERN,
    SourceStatus.ACTIVE,
)


@dataclass(frozen=True)
class SeverityResult:
    """The severity stage output for a single claim."""

    diagnostic: Diagnostic
    traffic_light: TrafficLight
    auto_pass_blocked: bool
    auto_passed: bool
    routed_to_review: bool


def _aggregate_cited_status(checks: list[CitationCheck]) -> ResolutionStatus:
    """Reduce every citation resolution to the single worst status (AC-SEVERITY-5).

    An empty list is an uncited claim: it resolves to OK so retrieval drives the result.
    """
    present = {c.resolution_status for c in checks}
    for status in _CITED_PRECEDENCE:
        if status in present:
            return status
    return ResolutionStatus.OK


def _aggregate_source_status(checks: list[CitationCheck]) -> SourceStatus:
    """Reduce every source posture to the worst; a missing posture counts as active."""
    present = {c.source_status for c in checks if c.source_status is not None}
    for status in _SOURCE_PRECEDENCE:
        if status in present:
            return status
    return SourceStatus.ACTIVE


def _diagnostic(
    *,
    label: JudgeLabel | None,
    confidence: float | None,
    cited_status: ResolutionStatus,
    source_status: SourceStatus,
    retrieval_mode: RetrievalMode | None,
    config: Config,
) -> tuple[Diagnostic, TrafficLight]:
    """The numeric-branch decision table (AC-SEVERITY-2), evaluated in order."""
    # A fabricated citation forces D5/red regardless of the label (AC-SEVERITY-5).
    if cited_status is ResolutionStatus.FABRICATED:
        return Diagnostic.D5, TrafficLight.RED

    source_active = source_status is SourceStatus.ACTIVE
    has_conf = confidence is not None

    if (
        label is JudgeLabel.SUPPORTED
        and cited_status is ResolutionStatus.OK
        and source_active
        and retrieval_mode is not RetrievalMode.CITED_ABSTRACT
        and has_conf
        and confidence >= config.high_conf
    ):
        return Diagnostic.D1, TrafficLight.GREEN

    if label is JudgeLabel.SUPPORTED and (
        not has_conf
        or confidence < config.high_conf
        or cited_status is ResolutionStatus.METADATA_MISMATCH
        or retrieval_mode is RetrievalMode.CITED_ABSTRACT
    ):
        return Diagnostic.D2, _d2_light(has_conf, confidence, config)

    if (
        retrieval_mode is RetrievalMode.NONE
        or cited_status is ResolutionStatus.UNKNOWN
        or cited_status is ResolutionStatus.UNRESOLVED
        or label is JudgeLabel.JUDGE_ERROR
        or label is None
    ):
        return Diagnostic.D3, TrafficLight.YELLOW

    if label is JudgeLabel.UNSUPPORTED and retrieval_mode is not RetrievalMode.NONE:
        return Diagnostic.D4, TrafficLight.YELLOW

    if label is JudgeLabel.CONTRADICTED:
        return Diagnostic.D5, TrafficLight.RED

    # Only a supported claim reaches here (for example a retracted source with otherwise
    # clean, high-confidence support). It is grounded with a gap: D2, capped below.
    return Diagnostic.D2, _d2_light(has_conf, confidence, config)


def _d2_light(has_conf: bool, confidence: float | None, config: Config) -> TrafficLight:
    """D2 is green only when a real confidence clears the borderline knob."""
    if has_conf and confidence >= config.borderline:
        return TrafficLight.GREEN
    return TrafficLight.YELLOW


_HUMAN_REVIEW_LIGHT: dict[JudgeLabel, TrafficLight] = {
    JudgeLabel.SUPPORTED: TrafficLight.GREEN,
    JudgeLabel.CONTRADICTED: TrafficLight.RED,
    JudgeLabel.UNSUPPORTED: TrafficLight.YELLOW,
}


def human_review_light(label: JudgeLabel) -> TrafficLight:
    """The traffic light for a claim a human has finished reviewing.

    A human review is a terminal, out-of-band authority on top of the pipeline rubric: once a
    person records a final verdict for a claim, that verdict decides the light, not the
    deterministic gates in `score_claim` (which is why a reviewer can promote a claim the
    pipeline could never auto-pass, e.g. a safety-critical claim they have personally checked).
    Anything other than a clean supported/contradicted/unsupported call is left at YELLOW: the
    claim still needs eyes rather than being asserted either way.
    """
    return _HUMAN_REVIEW_LIGHT.get(label, TrafficLight.YELLOW)


def score_claim(
    *,
    category: Category,
    label: JudgeLabel | None,
    confidence: float | None,
    citation_checks: list[CitationCheck],
    retrieval_mode: RetrievalMode | None,
    claim_text: str,
    config: Config,
) -> SeverityResult:
    """Map one claim's verdict and citation state to its severity outcome.

    Deterministic and side-effect free. See the module docstring for the two guards.
    """
    cited_status = _aggregate_cited_status(citation_checks)
    source_status = _aggregate_source_status(citation_checks)

    diagnostic, traffic_light = _diagnostic(
        label=label,
        confidence=confidence,
        cited_status=cited_status,
        source_status=source_status,
        retrieval_mode=retrieval_mode,
        config=config,
    )

    # AC-CITE-9: a retracted source or an expression of concern is never green.
    if traffic_light is TrafficLight.GREEN and source_status in (
        SourceStatus.RETRACTED,
        SourceStatus.CONCERN,
    ):
        traffic_light = TrafficLight.YELLOW

    auto_pass_blocked = not (
        traffic_light is TrafficLight.GREEN and category is not Category.SAFETY_CRITICAL
    )

    # AC-SAFETY-1..4: re-derive safety-criticality from the lexical oracle, independently
    # of the model's category, before any auto-pass. A green claim is forced to yellow,
    # red is left alone, and auto-pass is always blocked.
    is_safety = category is Category.SAFETY_CRITICAL or is_safety_critical_text(claim_text)
    if is_safety:
        if traffic_light is TrafficLight.GREEN:
            traffic_light = TrafficLight.YELLOW
        auto_pass_blocked = True

    # AC-ROUTING-1: a missing confidence never reached the judge and routes like a
    # below-threshold claim.
    routed_to_review = (
        traffic_light in (TrafficLight.RED, TrafficLight.YELLOW)
        or confidence is None
        or confidence < config.calibration_threshold
        or auto_pass_blocked
    )

    auto_passed = (
        traffic_light is TrafficLight.GREEN
        and category is not Category.SAFETY_CRITICAL
        and not routed_to_review
    )

    return SeverityResult(
        diagnostic=diagnostic,
        traffic_light=traffic_light,
        auto_pass_blocked=auto_pass_blocked,
        auto_passed=auto_passed,
        routed_to_review=routed_to_review,
    )
