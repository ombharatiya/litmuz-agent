"""Application-service layer: submit a memo for verification and run a job to completion.

Shared by the API (submit), the worker (run_job) and MCP. Contains no verification logic; it
wires litmuz_core.run_pipeline to the store and the queue and owns the job lifecycle,
idempotency, and failure isolation. The core pipeline already isolates single-claim faults
(judge_error, evidence_not_located); a failure that escapes it marks the job failed and
re-raises so the message is retried and eventually dead-lettered (AC-JOB-3).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from litmuz_core.config import Config
from litmuz_core.pipeline import run_pipeline
from litmuz_core.title import generate_title
from litmuz_store import (
    claim_job,
    count_jobs_since,
    create_job,
    fail_job,
    get_job,
    persist_report,
    set_job_title,
    update_job_progress,
)

from .queue import Queue


class SubmissionError(ValueError):
    """Rejected before any job row is written or anything is enqueued."""


class EmptyMemo(SubmissionError):
    pass


class SubmissionTooLarge(SubmissionError):
    pass


class QuotaExceeded(SubmissionError):
    """The user has used their weekly verification allowance for their tier."""

    def __init__(self, usage: dict) -> None:
        super().__init__("weekly quota exceeded")
        self.usage = usage


def _week_window(now: datetime) -> tuple[datetime, datetime]:
    """The current calendar week in UTC: (Monday 00:00, the following Monday 00:00)."""
    day_start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    start = day_start - timedelta(days=now.astimezone(UTC).weekday())
    return start, start + timedelta(days=7)


def _limit_for(tier: str, config: Config) -> int:
    return config.pro_weekly_limit if tier == "pro" else config.free_weekly_limit


def usage_for(
    app_conn,
    *,
    user_sub: str,
    tier: str,
    config: Config | None = None,
    now: datetime | None = None,
) -> dict:
    """This week's verification usage for a user, for the quota check and the /me/usage view."""
    config = config or Config()
    now = now or datetime.now(UTC)
    start, resets = _week_window(now)
    used = count_jobs_since(app_conn, user_sub, start)
    limit = _limit_for(tier, config)
    return {
        "tier": tier,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "resets_at": resets.isoformat(),
    }


def submit(
    *,
    memo: str,
    user_sub: str,
    app_conn,
    queue: Queue,
    config: Config | None = None,
    tier: str | None = None,
    now: datetime | None = None,
) -> str:
    """Validate, enforce the weekly quota, create the job, enqueue it, and return the job id.

    The byte-cap and empty checks run before any row is written or message enqueued, so an
    oversized or empty submission incurs no cost (AC-API-2, AC-DECOMP-5). When `tier` is given
    (auth enabled), the per-user weekly quota is enforced before the job is created, so an
    over-quota submission also incurs no cost and never enqueues. `tier` None means unlimited
    (dark-ship / open mode).
    """
    config = config or Config()
    if not memo or not memo.strip():
        raise EmptyMemo("memo is empty")
    if len(memo.encode("utf-8")) > config.max_input_bytes:
        raise SubmissionTooLarge(f"memo exceeds the {config.max_input_bytes} byte cap")
    if tier is not None:
        usage = usage_for(app_conn, user_sub=user_sub, tier=tier, config=config, now=now)
        if usage["used"] >= usage["limit"]:
            raise QuotaExceeded(usage)
    job_id = create_job(app_conn, user_sub=user_sub, memo=memo)
    queue.enqueue(job_id)
    return job_id


def run_job(
    job_id: str,
    *,
    app_conn,
    llm,
    metadata_client,
    retrieval_client,
    config: Config | None = None,
) -> str | None:
    """Run a queued job to completion. Idempotent under at-least-once delivery.

    Returns the report id, or None if another worker already claimed the job. A completed job
    returns its existing report id without re-running (no duplicate report).
    """
    config = config or Config()
    job = get_job(app_conn, job_id)
    if job is None:
        raise KeyError(f"unknown job {job_id}")
    if job["status"] == "completed" and job["report_id"] is not None:
        return str(job["report_id"])
    if not claim_job(app_conn, job_id):
        current = get_job(app_conn, job_id)
        if current and current["status"] == "completed" and current["report_id"] is not None:
            return str(current["report_id"])
        return None

    # Name the session from its memo, using the cheap title model. Best-effort: a naming failure
    # must never fail the verification, and an empty title falls back to a snippet at read time.
    if not (job.get("title") or "").strip():
        title = generate_title(job["memo"], llm=llm, config=config)
        if title:
            set_job_title(app_conn, job_id, title)

    def progress(stage: str, done: int, total: int) -> None:
        update_job_progress(app_conn, job_id, stage=stage, claims_done=done, claims_total=total)

    try:
        report = run_pipeline(
            job["memo"],
            llm=llm,
            metadata_client=metadata_client,
            retrieval_client=retrieval_client,
            config=config,
            job_id=str(job_id),
            on_progress=progress,
        )
        persisted = persist_report(app_conn, report, user_sub=job["user_sub"])
        return persisted.id
    except Exception as exc:
        fail_job(app_conn, job_id, error=f"{type(exc).__name__}: {exc}")
        raise
