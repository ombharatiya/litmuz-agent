import json

import pytest
from pydantic import ValidationError

from litmuz_core.config import IdType, MatchResult, ResolutionStatus, SourceStatus
from litmuz_core.schemas import (
    CitationCheck,
    Evidence,
    Report,
    SourceSpan,
    export_report_json_schema,
)


def test_source_span_rejects_disordered_bounds():
    SourceSpan(start=0, end=5)
    with pytest.raises(ValidationError):
        SourceSpan(start=5, end=2)
    with pytest.raises(ValidationError):
        SourceSpan(start=-1, end=3)


def test_evidence_requires_exactly_one_of_span_or_marker():
    Evidence(evidence_sentence="p53 induces apoptosis.", source_locator={"section": "results"})
    Evidence(evidence_not_located=True)
    with pytest.raises(ValidationError):
        Evidence()  # neither
    with pytest.raises(ValidationError):
        Evidence(evidence_sentence="x", evidence_not_located=True)  # both


def test_citation_check_defaults_matches_to_not_applicable():
    cc = CitationCheck(
        identifier="pmid:12345",
        id_type=IdType.PMID,
        resolution_status=ResolutionStatus.OK,
        source_status=SourceStatus.ACTIVE,
    )
    assert cc.title_match is MatchResult.NOT_APPLICABLE
    assert cc.author_match is MatchResult.NOT_APPLICABLE


def test_extra_fields_are_forbidden():
    with pytest.raises(ValidationError):
        SourceSpan(start=0, end=1, sneaky=True)


def test_report_json_schema_exposes_the_safety_critical_fields():
    schema = export_report_json_schema()
    text = json.dumps(schema)
    for field in (
        "auto_passed",
        "auto_pass_blocked",
        "reviewer_actions",
        "effective_verdict",
        "evidence_not_located",
        "source_status",
        "unclaimed_spans",
    ):
        assert field in text, f"{field} missing from exported report schema"


def test_minimal_report_constructs():
    Report(id="r1", job_id="j1", memo_hash="deadbeef", created_at="2026-07-03T00:00:00Z")
