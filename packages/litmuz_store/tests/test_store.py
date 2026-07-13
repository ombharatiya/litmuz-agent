"""Round-trip persistence and the effective_verdict projection (AC-STORE-1, AC-REPORT-7)."""

from litmuz_core.config import (
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
from litmuz_core.schemas import (
    CitationCheck,
    CitedId,
    Claim,
    Evidence,
    Report,
    SourceSpan,
    Verdict,
)
from litmuz_store.store import (
    add_reviewer_action,
    create_job,
    get_job,
    list_queue,
    persist_report,
    read_report,
)


def _sample_report(job_id: str) -> Report:
    grounded = Claim(
        id="c1",
        ordinal=0,
        text="TP53 is a tumour suppressor.",
        source_span=SourceSpan(start=0, end=28),
        cited_ids=[CitedId(id_type=IdType.PMID, value="12345")],
        citation_checks=[
            CitationCheck(
                identifier="pmid:12345",
                id_type=IdType.PMID,
                resolution_status=ResolutionStatus.OK,
                source_status=SourceStatus.ACTIVE,
                author_match=MatchResult.TRUE,
                year_match=MatchResult.TRUE,
                resolver_path="esummary",
            )
        ],
        retrieval_mode=RetrievalMode.CITED_FULLTEXT,
        evidence=Evidence(
            evidence_sentence="TP53 is a tumour suppressor.",
            source_locator={"source_id": "pmid:12345"},
        ),
        verdict=Verdict(label=JudgeLabel.SUPPORTED, confidence=0.95, rationale="supported"),
        category=Category.MECHANISTIC,
        diagnostic=Diagnostic.D1,
        traffic_light=TrafficLight.GREEN,
        auto_pass_blocked=False,
        auto_passed=True,
        routed_to_review=False,
        effective_verdict=Verdict(
            label=JudgeLabel.SUPPORTED, confidence=0.95, rationale="supported"
        ),
    )
    fabricated = Claim(
        id="c2",
        ordinal=1,
        text="A fabricated result was reported.",
        source_span=SourceSpan(start=29, end=62),
        cited_ids=[CitedId(id_type=IdType.PMID, value="99999999")],
        citation_checks=[
            CitationCheck(
                identifier="pmid:99999999",
                id_type=IdType.PMID,
                resolution_status=ResolutionStatus.FABRICATED,
                resolver_path="esummary",
            )
        ],
        retrieval_mode=RetrievalMode.NONE,
        evidence=Evidence(evidence_not_located=True),
        verdict=None,
        category=Category.CITATION,
        diagnostic=Diagnostic.D5,
        traffic_light=TrafficLight.RED,
        auto_pass_blocked=True,
        auto_passed=False,
        routed_to_review=True,
        effective_verdict=None,
    )
    return Report(
        id="placeholder",
        job_id=job_id,
        memo_hash="abc123",
        model_versions={"judge": "claude-opus-4-8"},
        rubric_version="1",
        summary_counts={
            "total": 2,
            "by_traffic_light": {"green": 1, "red": 1},
            "by_category": {"mechanistic": 1, "citation": 1},
            "routed_to_review": 1,
        },
        unclaimed_spans=[SourceSpan(start=63, end=80)],
        claims=[grounded, fabricated],
        created_at="2026-07-03T00:00:00Z",
    )


def test_round_trip_is_field_exact(app_conn, api_conn):
    job_id = create_job(app_conn, user_sub="u1")
    persisted = persist_report(app_conn, _sample_report(job_id), user_sub="u1")

    fetched = read_report(api_conn, persisted.id)
    assert fetched == persisted  # exact through the database

    # content preserved (the surrogate claim ids replace the in-report c1/c2)
    assert [c.text for c in persisted.claims] == [
        "TP53 is a tumour suppressor.",
        "A fabricated result was reported.",
    ]
    assert persisted.claims[0].traffic_light is TrafficLight.GREEN
    assert persisted.claims[0].verdict.label is JudgeLabel.SUPPORTED
    assert persisted.claims[0].citation_checks[0].resolution_status is ResolutionStatus.OK
    assert persisted.claims[1].traffic_light is TrafficLight.RED
    assert persisted.claims[1].verdict is None
    assert persisted.claims[1].evidence.evidence_not_located is True
    assert persisted.memo_hash == "abc123"
    assert persisted.summary_counts["routed_to_review"] == 1

    job = get_job(app_conn, job_id)
    assert job["status"] == "completed"
    assert str(job["report_id"]) == persisted.id


def test_reading_a_missing_report_returns_none(api_conn):
    assert read_report(api_conn, "00000000-0000-4000-8000-000000000000") is None


def test_effective_verdict_latest_override_wins(app_conn, api_conn):
    job_id = create_job(app_conn, user_sub="u1")
    persisted = persist_report(app_conn, _sample_report(job_id), user_sub="u1")
    claim_id = persisted.claims[0].id

    add_reviewer_action(
        api_conn,
        claim_id,
        reviewer_identity="rev1",
        action="override_verdict",
        new_verdict={"label": "contradicted", "confidence": None, "rationale": "human override"},
    )
    claim = _claim(read_report(api_conn, persisted.id), claim_id)
    assert claim.verdict.label is JudgeLabel.SUPPORTED  # pipeline verdict is never mutated
    assert claim.effective_verdict.label is JudgeLabel.CONTRADICTED
    assert len(claim.reviewer_actions) == 1
    # The human decision wins over the pipeline's own light too (this claim was pipeline-GREEN).
    assert claim.traffic_light is TrafficLight.GREEN  # pipeline light is never mutated
    assert claim.effective_traffic_light is TrafficLight.RED
    assert claim.reviewed is True
    assert claim.review_action == "override_verdict"
    assert claim.reviewed_by == "rev1"

    add_reviewer_action(api_conn, claim_id, reviewer_identity="rev2", action="accept")
    claim = _claim(read_report(api_conn, persisted.id), claim_id)
    assert claim.effective_verdict.label is JudgeLabel.CONTRADICTED  # accept does not change it
    assert len(claim.reviewer_actions) == 2
    # An accept after an override is itself the latest terminal action: it is now of record.
    assert claim.review_action == "accept"
    assert claim.reviewed_by == "rev2"
    assert claim.effective_traffic_light is TrafficLight.RED  # verdict/light still stand

    add_reviewer_action(
        api_conn,
        claim_id,
        reviewer_identity="rev3",
        action="override_verdict",
        new_verdict={"label": "unsupported", "confidence": None, "rationale": "reconsidered"},
    )
    claim = _claim(read_report(api_conn, persisted.id), claim_id)
    assert claim.effective_verdict.label is JudgeLabel.UNSUPPORTED  # latest override wins
    assert claim.effective_traffic_light is TrafficLight.YELLOW


def test_add_note_does_not_mark_a_claim_reviewed(app_conn, api_conn):
    job_id = create_job(app_conn, user_sub="u1")
    persisted = persist_report(app_conn, _sample_report(job_id), user_sub="u1")
    claim_id = persisted.claims[1].id  # the routed, fabricated (red) claim

    add_reviewer_action(
        api_conn, claim_id, reviewer_identity="rev1", action="add_note", note="looking into it"
    )
    claim = _claim(read_report(api_conn, persisted.id), claim_id)
    assert claim.reviewed is False
    assert claim.reviewed_by is None
    assert claim.effective_traffic_light is TrafficLight.RED  # unchanged
    assert list_queue(api_conn, user_sub="u1")  # still in the queue


def test_queue_lists_only_flagged_claims(app_conn, api_conn):
    job_id = create_job(app_conn, user_sub="u1")
    persisted = persist_report(app_conn, _sample_report(job_id), user_sub="u1")
    queue = list_queue(api_conn, user_sub="u1")
    assert len(queue) == 1  # only the routed (red) claim
    assert queue[0]["claim_id"] == persisted.claims[1].id
    assert queue[0]["traffic_light"] == "red"


def test_a_terminal_review_action_removes_the_claim_from_the_queue(app_conn, api_conn):
    job_id = create_job(app_conn, user_sub="u1")
    persisted = persist_report(app_conn, _sample_report(job_id), user_sub="u1")
    claim_id = persisted.claims[1].id

    assert len(list_queue(api_conn, user_sub="u1")) == 1
    add_reviewer_action(api_conn, claim_id, reviewer_identity="rev1", action="accept")
    assert list_queue(api_conn, user_sub="u1") == []


def _claim(report, claim_id):
    return next(c for c in report.claims if c.id == claim_id)
