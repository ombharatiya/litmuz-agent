"""Pydantic v2 models: the wire/report contract.

These models ARE the report JSON schema (AC-REPORT-2 exports it from here), and
they validate at construction so an invalid report can never be emitted. Fields a
later pipeline stage fills are optional now; the deterministic citation layer
(Phase 1) populates ``cited_ids``, ``attribution`` and ``citation_checks``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from .config import (
    Category,
    Diagnostic,
    IdType,
    JudgeLabel,
    MatchResult,
    ResolutionStatus,
    RetrievalMode,
    SourceStatus,
    TrafficLight,
)

_STRICT = ConfigDict(extra="forbid")


class SourceSpan(BaseModel):
    model_config = _STRICT
    start: int
    end: int

    @model_validator(mode="after")
    def _ordered(self) -> SourceSpan:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"invalid span: start={self.start} end={self.end}")
        return self


class CitedId(BaseModel):
    model_config = _STRICT
    id_type: IdType
    value: str


class ClaimAttribution(BaseModel):
    """What the memo claims about a citation (from the reference entry, if any).

    Empty fields mean 'no attribution supplied' → matches record as NOT_APPLICABLE,
    never as a mismatch (AC-CITE-8).
    """

    model_config = _STRICT
    title: str | None = None
    surnames: list[str] = []
    year: int | None = None


class CitationCheck(BaseModel):
    """Deterministic (no-LLM) result of resolving one citation."""

    model_config = _STRICT
    identifier: str
    id_type: IdType
    resolution_status: ResolutionStatus
    source_status: SourceStatus | None = None  # None when the source was not found
    title_match: MatchResult = MatchResult.NOT_APPLICABLE
    author_match: MatchResult = MatchResult.NOT_APPLICABLE
    year_match: MatchResult = MatchResult.NOT_APPLICABLE
    resolver_path: str = ""


class Passage(BaseModel):
    """A retrieved evidence passage the judge reads (produced by the retrieve stage)."""

    model_config = _STRICT
    source_id: str
    text: str
    section: str | None = None
    offset: int | None = None
    retrieval_mode: RetrievalMode


class Evidence(BaseModel):
    """Typed union: a verbatim span, or an explicit not-located marker (AC-REPORT-5)."""

    model_config = _STRICT
    evidence_sentence: str | None = None
    source_locator: dict | None = None
    evidence_not_located: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> Evidence:
        has_span = self.evidence_sentence is not None
        if has_span == self.evidence_not_located:
            raise ValueError(
                "evidence must carry either an evidence_sentence or evidence_not_located=True"
            )
        return self


class Verdict(BaseModel):
    model_config = _STRICT
    label: JudgeLabel
    confidence: float | None = None  # None for any claim that never reached the judge (A3)
    rationale: str = ""


class ReviewerAction(BaseModel):
    model_config = _STRICT
    reviewer_identity: str
    action: str  # accept | override_verdict | add_note
    prior_verdict: dict | None = None
    new_verdict: dict | None = None
    note: str = ""
    created_at: str


class Claim(BaseModel):
    model_config = _STRICT
    id: str
    ordinal: int
    text: str
    source_span: SourceSpan
    cited_ids: list[CitedId] = []
    attribution: ClaimAttribution | None = None
    citation_checks: list[CitationCheck] = []
    retrieval_mode: RetrievalMode | None = None
    evidence: Evidence | None = None
    verdict: Verdict | None = None
    category: Category | None = None
    diagnostic: Diagnostic | None = None
    traffic_light: TrafficLight | None = None
    auto_pass_blocked: bool | None = None
    auto_passed: bool | None = None
    routed_to_review: bool | None = None
    reviewer_actions: list[ReviewerAction] = []
    effective_verdict: Verdict | None = None
    # Projected at read time from reviewer_actions (never stored): the light after a human's
    # terminal decision, and who made it and when. None/False when no accept or override has
    # been recorded, in which case the pipeline traffic_light is still the claim's light.
    effective_traffic_light: TrafficLight | None = None
    reviewed: bool = False
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_action: str | None = None  # "accept" | "override_verdict"


class Report(BaseModel):
    model_config = _STRICT
    id: str
    job_id: str
    memo_hash: str
    model_versions: dict = {}
    rubric_version: str = ""
    summary_counts: dict = {}
    unclaimed_spans: list[SourceSpan] = []
    claims: list[Claim] = []
    created_at: str


def export_report_json_schema() -> dict:
    """The published JSON schema (AC-REPORT-2)."""
    return Report.model_json_schema()
