"""Service-layer job lifecycle: submit, run, idempotency, concurrency, failure isolation,
and the cost spy (Phase 4). Shared pipeline fakes, a real Postgres via app_conn."""

from datetime import UTC

import pytest

from litmuz_core.config import Config, TrafficLight
from litmuz_core.testing import (
    DEMO_MEMO,
    FakeMetadataClient,
    FakePipelineLlm,
    FakeRetrievalClient,
)
from litmuz_service.jobs import EmptyMemo, SubmissionTooLarge, run_job, submit
from litmuz_service.queue import InMemoryQueue
from litmuz_store import claim_job, get_job, read_report


def _run(app_conn, llm=None, metadata=None):
    queue = InMemoryQueue()
    job_id = submit(memo=DEMO_MEMO, user_sub="u1", app_conn=app_conn, queue=queue)
    report_id = run_job(
        job_id,
        app_conn=app_conn,
        llm=llm or FakePipelineLlm(),
        metadata_client=metadata or FakeMetadataClient(),
        retrieval_client=FakeRetrievalClient(),
    )
    return job_id, report_id


def _count(app_conn, table: str) -> int:
    with app_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        return cur.fetchone()[0]


# --- submit: pre-pipeline validation, no cost on rejection ---


def test_submit_creates_job_and_enqueues(app_conn):
    queue = InMemoryQueue()
    job_id = submit(memo=DEMO_MEMO, user_sub="u1", app_conn=app_conn, queue=queue)
    job = get_job(app_conn, job_id)
    assert job["status"] == "queued"
    assert job["memo"] == DEMO_MEMO
    assert queue.messages == [job_id]


def test_submit_rejects_oversized_before_any_write(app_conn):
    queue = InMemoryQueue()
    big = "x" * (Config().max_input_bytes + 1)
    with pytest.raises(SubmissionTooLarge):
        submit(memo=big, user_sub="u1", app_conn=app_conn, queue=queue)
    assert _count(app_conn, "jobs") == 0  # no job row written
    assert queue.messages == []  # nothing enqueued


def test_submit_rejects_empty(app_conn):
    with pytest.raises(EmptyMemo):
        submit(memo="   ", user_sub="u1", app_conn=app_conn, queue=InMemoryQueue())
    assert _count(app_conn, "jobs") == 0


# --- run_job: end to end, idempotency, concurrency, failure isolation ---


def test_run_job_end_to_end_with_cost_spy(app_conn):
    llm = FakePipelineLlm()
    job_id, report_id = _run(app_conn, llm=llm)

    report = read_report(app_conn, report_id)
    by = {c.text: c for c in report.claims}
    assert by["TP53 loss drives tumour proliferation [1]."].traffic_light is TrafficLight.GREEN
    assert by["The recommended dose was 5 mg daily [1]."].auto_passed is False  # safety held
    assert by["A fabricated result was reported [2]."].traffic_light is TrafficLight.RED

    job = get_job(app_conn, job_id)
    assert job["status"] == "completed"
    assert str(job["report_id"]) == report_id
    assert job["claims_done"] == job["claims_total"] == 3  # progress reached the end

    # AC-NFR-3: the judge ran only on the two non-fabricated claims.
    assert llm.judge_calls == 2


def test_run_job_names_the_session_from_the_memo(app_conn):
    # The worker titles the session with the cheap model so the studio list is identifiable.
    job_id, _ = _run(app_conn)
    assert get_job(app_conn, job_id)["title"] == "A TP53 study in carcinoma"


def test_run_job_is_idempotent_on_redelivery(app_conn):
    job_id, report_id = _run(app_conn)
    again = run_job(
        job_id,
        app_conn=app_conn,
        llm=FakePipelineLlm(),
        metadata_client=FakeMetadataClient(),
        retrieval_client=FakeRetrievalClient(),
    )
    assert again == report_id
    assert _count(app_conn, "reports") == 1


def test_run_job_skips_a_claimed_job(app_conn):
    queue = InMemoryQueue()
    job_id = submit(memo=DEMO_MEMO, user_sub="u1", app_conn=app_conn, queue=queue)
    assert claim_job(app_conn, job_id) is True  # a concurrent worker claims it first
    result = run_job(
        job_id,
        app_conn=app_conn,
        llm=FakePipelineLlm(),
        metadata_client=FakeMetadataClient(),
        retrieval_client=FakeRetrievalClient(),
    )
    assert result is None
    assert _count(app_conn, "reports") == 0


def test_worker_error_marks_job_failed_and_reraises(app_conn):
    queue = InMemoryQueue()
    job_id = submit(memo=DEMO_MEMO, user_sub="u1", app_conn=app_conn, queue=queue)
    with pytest.raises(RuntimeError):
        run_job(
            job_id,
            app_conn=app_conn,
            llm=FakePipelineLlm(),
            metadata_client=FakeMetadataClient(raise_error=True),  # escapes the pipeline
            retrieval_client=FakeRetrievalClient(),
        )
    job = get_job(app_conn, job_id)
    assert job["status"] == "failed"
    assert "RuntimeError" in job["error"]
    assert _count(app_conn, "reports") == 0  # no partial report shown as complete


def test_single_claim_judge_fault_does_not_fail_the_job(app_conn):
    # AC-JUDGE-7: a judge fault degrades only the affected claims; the job still completes.
    job_id, report_id = _run(app_conn, llm=FakePipelineLlm(judge_mode="raise"))
    assert report_id is not None
    job = get_job(app_conn, job_id)
    assert job["status"] == "completed"
    report = read_report(app_conn, report_id)
    judged = [c for c in report.claims if c.verdict is not None]
    assert judged and all(c.verdict.label.value == "judge_error" for c in judged)


# --- weekly quota (freemium) ---


def test_free_tier_allows_two_then_blocks(app_conn):
    from litmuz_service.jobs import QuotaExceeded

    queue = InMemoryQueue()
    submit(memo=DEMO_MEMO, user_sub="q1", app_conn=app_conn, queue=queue, tier="free")
    submit(memo=DEMO_MEMO, user_sub="q1", app_conn=app_conn, queue=queue, tier="free")
    assert len(queue.messages) == 2

    with pytest.raises(QuotaExceeded) as exc:
        submit(memo=DEMO_MEMO, user_sub="q1", app_conn=app_conn, queue=queue, tier="free")
    # Rejected before any cost: no third job row, nothing enqueued.
    assert _count(app_conn, "jobs") == 2
    assert len(queue.messages) == 2
    assert exc.value.usage["used"] == 2
    assert exc.value.usage["limit"] == 2
    assert exc.value.usage["remaining"] == 0


def test_quota_is_per_user(app_conn):
    queue = InMemoryQueue()
    submit(memo=DEMO_MEMO, user_sub="a", app_conn=app_conn, queue=queue, tier="free")
    submit(memo=DEMO_MEMO, user_sub="a", app_conn=app_conn, queue=queue, tier="free")
    # A different user is unaffected by a's usage.
    submit(memo=DEMO_MEMO, user_sub="b", app_conn=app_conn, queue=queue, tier="free")
    assert _count(app_conn, "jobs") == 3


def test_pro_tier_allows_far_more(app_conn):
    queue = InMemoryQueue()
    for _ in range(5):
        submit(memo=DEMO_MEMO, user_sub="pro1", app_conn=app_conn, queue=queue, tier="pro")
    assert _count(app_conn, "jobs") == 5


def test_no_tier_is_unlimited(app_conn):
    queue = InMemoryQueue()
    for _ in range(4):
        submit(memo=DEMO_MEMO, user_sub="open", app_conn=app_conn, queue=queue, tier=None)
    assert _count(app_conn, "jobs") == 4


def test_usage_counts_only_the_current_week(app_conn):
    from datetime import datetime, timedelta

    from litmuz_service.jobs import usage_for

    queue = InMemoryQueue()
    submit(memo=DEMO_MEMO, user_sub="w1", app_conn=app_conn, queue=queue, tier="free")
    now = datetime.now(UTC)
    assert usage_for(app_conn, user_sub="w1", tier="free", now=now)["used"] == 1
    # Two weeks on, this week's window excludes the earlier job.
    later = now + timedelta(days=14)
    assert usage_for(app_conn, user_sub="w1", tier="free", now=later)["used"] == 0
