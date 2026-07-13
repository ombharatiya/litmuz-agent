"""Provenance persistence over PostgreSQL (AC-STORE-1, AC-REPORT-7).

Functions take a psycopg connection so the caller controls which least-privilege role is
used: the worker persists as litmuz_app, the API reads and appends reviewer actions as
litmuz_api. Verdicts and reviewer actions are append-only; effective_verdict is a projection
over the reviewer-action history (latest override wins), never a mutable stored column.
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from litmuz_core.config import JudgeLabel
from litmuz_core.schemas import Report
from litmuz_core.severity import human_review_light

# Reviewer actions that resolve a claim and remove it from the review queue. A bare add_note
# is commentary only: it neither resolves the claim nor changes its effective light.
_TERMINAL_REVIEW_ACTIONS = ("accept", "override_verdict")


def _v(enum_or_none) -> str | None:
    return enum_or_none.value if enum_or_none is not None else None


def create_job(conn, *, user_sub: str, memo: str = "", mode: str = "literature") -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO jobs (user_sub, status, memo, mode) VALUES (%s, 'queued', %s, %s) "
            "RETURNING job_id",
            (user_sub, memo, mode),
        )
        job_id = str(cur.fetchone()[0])
    conn.commit()
    return job_id


def get_job(conn, job_id: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM jobs WHERE job_id = %s", (job_id,))
        return cur.fetchone()


def count_jobs_since(conn, user_sub: str, since) -> int:
    """How many jobs a user has submitted at or after `since` (drives the weekly quota).

    Served by the (user_sub, created_at) index. `since` is a timezone-aware datetime.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM jobs WHERE user_sub = %s AND created_at >= %s",
            (user_sub, since),
        )
        return int(cur.fetchone()[0])


def list_jobs(conn, user_sub: str, limit: int = 50) -> list[dict]:
    """A user's jobs, newest first, for the studio session list (served by the
    (user_sub, created_at DESC) index). Carries the generated title and a memo snippet so the
    list is identifiable; the client shows the title and falls back to the snippet."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT job_id, status, stage, report_id, created_at, title, memo, mode FROM jobs "
            "WHERE user_sub = %s ORDER BY created_at DESC LIMIT %s",
            (user_sub, limit),
        )
        rows = cur.fetchall()
    return [
        {
            "job_id": str(row["job_id"]),
            "status": row["status"],
            "stage": row["stage"],
            "report_id": str(row["report_id"]) if row["report_id"] else None,
            "created_at": row["created_at"].isoformat(),
            "title": row["title"] or "",
            "memo_snippet": _memo_snippet(row["memo"]),
            "mode": row["mode"],
        }
        for row in rows
    ]


def set_job_title(conn, job_id: str, title: str) -> None:
    """Store the generated session title. Best-effort naming, so it never touches status."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET title = %s, updated_at = now() WHERE job_id = %s",
            (title, job_id),
        )
    conn.commit()


def _memo_snippet(memo: str | None, limit: int = 80) -> str:
    """First ~limit chars of the memo, collapsed to a single line."""
    if not memo:
        return ""
    single_line = " ".join(memo.split())
    return single_line[:limit]


def claim_job(conn, job_id: str, *, stale_running_timeout_s: int = 600) -> bool:
    """Atomically move a queued, failed, or stale-running job to running. Returns True if
    this caller won it.

    At-least-once delivery means the same job may arrive twice; only one caller claims it, so
    a redelivered or concurrent message never produces a duplicate report (AC-JOB-3/AC-JOB-5).

    A 'running' row whose updated_at is older than stale_running_timeout_s is presumed
    orphaned by a worker that died mid-run (deploy restart, OOM, task eviction) rather than
    still in progress, and is reclaimed exactly like a failed job. Without this, a job a dead
    worker claimed would stay at 'running' forever: no future redelivery could ever reclaim
    it, since 'running' was the one status claim_job never matched.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'running', updated_at = now() "
            "WHERE job_id = %s AND ("
            "  status IN ('queued', 'failed') "
            "  OR (status = 'running' AND updated_at < now() - (%s * interval '1 second'))"
            ") RETURNING job_id",
            (job_id, stale_running_timeout_s),
        )
        claimed = cur.fetchone() is not None
    conn.commit()
    return claimed


def update_job_progress(
    conn, job_id: str, *, stage: str, claims_done: int, claims_total: int
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET stage = %s, claims_done = %s, claims_total = %s, updated_at = now() "
            "WHERE job_id = %s",
            (stage, claims_done, claims_total, job_id),
        )
    conn.commit()


def fail_job(conn, job_id: str, *, error: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'failed', error = %s, updated_at = now() WHERE job_id = %s",
            (error, job_id),
        )
    conn.commit()


def persist_report(conn, report: Report, *, user_sub: str) -> Report:
    """Write a completed report and its claims, then mark the job completed.

    The report_id and per-claim claim_id are generated by the database (surrogate uuids);
    the report's in-memory ids are placeholders and are not used. Returns the stored report
    read back through :func:`read_report`, so the return value is exactly what a later read
    yields.

    Idempotent per job: if a report for this job already exists (the stale-running reclaim in
    claim_job can briefly overlap a still-live worker), the unique index on reports.job_id
    turns this write into a no-op and the existing report is returned unchanged, so an overlap
    never produces a duplicate report or re-flips the job's status (AC-JOB-5).
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reports (job_id, user_sub, memo_hash, model_versions, "
            "rubric_version, summary_counts, unclaimed_spans) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (job_id) DO NOTHING "
            "RETURNING report_id",
            (
                report.job_id,
                user_sub,
                report.memo_hash,
                Jsonb(report.model_versions),
                report.rubric_version,
                Jsonb(report.summary_counts),
                Jsonb([span.model_dump() for span in report.unclaimed_spans]),
            ),
        )
        row = cur.fetchone()
        if row is None:
            # Another worker already persisted this job's report. Return it as-is; do not write
            # claims or touch job status a second time.
            cur.execute("SELECT report_id FROM reports WHERE job_id = %s", (report.job_id,))
            existing_report_id = str(cur.fetchone()[0])
            conn.rollback()
            return read_report(conn, existing_report_id)
        report_id = str(row[0])

        for claim in report.claims:
            cur.execute(
                "INSERT INTO claims (report_id, local_id, ordinal, text, source_span, "
                "category, diagnostic, traffic_light, auto_pass_blocked, auto_passed, "
                "routed_to_review, retrieval_mode) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING claim_id",
                (
                    report_id,
                    claim.id,
                    claim.ordinal,
                    claim.text,
                    Jsonb(claim.source_span.model_dump()),
                    _v(claim.category),
                    _v(claim.diagnostic),
                    _v(claim.traffic_light),
                    claim.auto_pass_blocked,
                    claim.auto_passed,
                    claim.routed_to_review,
                    _v(claim.retrieval_mode),
                ),
            )
            claim_id = str(cur.fetchone()[0])

            for cited in claim.cited_ids:
                cur.execute(
                    "INSERT INTO cited_ids (claim_id, id_type, id_value) VALUES (%s, %s, %s)",
                    (claim_id, cited.id_type.value, cited.value),
                )
            for check in claim.citation_checks:
                cur.execute(
                    "INSERT INTO citation_checks (claim_id, identifier, id_type, "
                    "resolution_status, source_status, title_match, author_match, "
                    "year_match, resolver_path) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        claim_id,
                        check.identifier,
                        check.id_type.value,
                        check.resolution_status.value,
                        _v(check.source_status),
                        check.title_match.value,
                        check.author_match.value,
                        check.year_match.value,
                        check.resolver_path,
                    ),
                )
            if claim.evidence is not None:
                locator = claim.evidence.source_locator
                cur.execute(
                    "INSERT INTO evidence (claim_id, evidence_sentence, source_locator, "
                    "evidence_not_located) VALUES (%s, %s, %s, %s)",
                    (
                        claim_id,
                        claim.evidence.evidence_sentence,
                        Jsonb(locator) if locator is not None else None,
                        claim.evidence.evidence_not_located,
                    ),
                )
            if claim.verdict is not None:
                cur.execute(
                    "INSERT INTO verdicts (claim_id, label, confidence, rationale) "
                    "VALUES (%s, %s, %s, %s)",
                    (
                        claim_id,
                        claim.verdict.label.value,
                        claim.verdict.confidence,
                        claim.verdict.rationale,
                    ),
                )

        cur.execute(
            "UPDATE jobs SET status = 'completed', report_id = %s, updated_at = now() "
            "WHERE job_id = %s",
            (report_id, report.job_id),
        )
    conn.commit()
    return read_report(conn, report_id)


def add_reviewer_action(
    conn,
    claim_id: str,
    *,
    reviewer_identity: str,
    action: str,
    note: str = "",
    new_verdict: dict | None = None,
) -> None:
    """Append a reviewer action (AC-QUEUE-2). Never mutates the pipeline verdict."""
    with conn.cursor(row_factory=dict_row) as cur:
        prior = _pipeline_verdict(cur, claim_id)
        cur.execute(
            "INSERT INTO reviewer_actions (claim_id, reviewer_identity, action, "
            "prior_verdict, new_verdict, note) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                claim_id,
                reviewer_identity,
                action,
                Jsonb(prior) if prior is not None else None,
                Jsonb(new_verdict) if new_verdict is not None else None,
                note,
            ),
        )
    conn.commit()


def read_report(conn, report_id: str) -> Report | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM reports WHERE report_id = %s", (report_id,))
        report_row = cur.fetchone()
        if report_row is None:
            return None
        cur.execute("SELECT * FROM claims WHERE report_id = %s ORDER BY ordinal", (report_id,))
        claim_rows = cur.fetchall()
        claims = [_read_claim(cur, row) for row in claim_rows]

    return Report.model_validate(
        {
            "id": str(report_id),
            "job_id": str(report_row["job_id"]),
            "memo_hash": report_row["memo_hash"],
            "model_versions": report_row["model_versions"],
            "rubric_version": report_row["rubric_version"],
            "summary_counts": report_row["summary_counts"],
            "unclaimed_spans": report_row["unclaimed_spans"],
            "claims": claims,
            "created_at": report_row["created_at"].isoformat(),
        }
    )


def _read_claim(cur, row: dict) -> dict:
    claim_id = row["claim_id"]
    cur.execute(
        "SELECT id_type, id_value FROM cited_ids WHERE claim_id = %s ORDER BY id", (claim_id,)
    )
    cited_ids = [{"id_type": r["id_type"], "value": r["id_value"]} for r in cur.fetchall()]
    cur.execute("SELECT * FROM citation_checks WHERE claim_id = %s ORDER BY id", (claim_id,))
    checks = [_check_dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM evidence WHERE claim_id = %s", (claim_id,))
    evidence_row = cur.fetchone()
    verdict = _pipeline_verdict(cur, claim_id)
    actions = _reviewer_actions(cur, claim_id)
    review = _review_meta(actions)
    return {
        "id": str(claim_id),
        "ordinal": row["ordinal"],
        "text": row["text"],
        "source_span": row["source_span"],
        "cited_ids": cited_ids,
        "attribution": None,
        "citation_checks": checks,
        "retrieval_mode": row["retrieval_mode"],
        "evidence": _evidence_dict(evidence_row),
        "verdict": verdict,
        "category": row["category"],
        "diagnostic": row["diagnostic"],
        "traffic_light": row["traffic_light"],
        "auto_pass_blocked": row["auto_pass_blocked"],
        "auto_passed": row["auto_passed"],
        "routed_to_review": row["routed_to_review"],
        "reviewer_actions": actions,
        "effective_verdict": _effective_verdict(verdict, actions),
        "effective_traffic_light": _effective_light(row["traffic_light"], actions),
        **review,
    }


def _check_dict(row: dict) -> dict:
    return {
        "identifier": row["identifier"],
        "id_type": row["id_type"],
        "resolution_status": row["resolution_status"],
        "source_status": row["source_status"],
        "title_match": row["title_match"],
        "author_match": row["author_match"],
        "year_match": row["year_match"],
        "resolver_path": row["resolver_path"],
    }


def _evidence_dict(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "evidence_sentence": row["evidence_sentence"],
        "source_locator": row["source_locator"],
        "evidence_not_located": row["evidence_not_located"],
    }


def _pipeline_verdict(cur, claim_id) -> dict | None:
    cur.execute(
        "SELECT label, confidence, rationale FROM verdicts WHERE claim_id = %s "
        "ORDER BY seq DESC LIMIT 1",
        (claim_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    confidence = row["confidence"]
    return {
        "label": row["label"],
        "confidence": float(confidence) if confidence is not None else None,
        "rationale": row["rationale"],
    }


def _reviewer_actions(cur, claim_id) -> list[dict]:
    cur.execute(
        "SELECT reviewer_identity, action, prior_verdict, new_verdict, note, created_at "
        "FROM reviewer_actions WHERE claim_id = %s ORDER BY seq",
        (claim_id,),
    )
    return [
        {
            "reviewer_identity": r["reviewer_identity"],
            "action": r["action"],
            "prior_verdict": r["prior_verdict"],
            "new_verdict": r["new_verdict"],
            "note": r["note"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in cur.fetchall()
    ]


def _effective_verdict(pipeline_verdict: dict | None, actions: list[dict]) -> dict | None:
    """Latest override wins (AC-REPORT-7). accept and add_note leave the verdict unchanged."""
    effective: dict | None = pipeline_verdict
    for action in actions:  # ordered oldest to newest
        if action["action"] == "override_verdict" and action["new_verdict"] is not None:
            effective = action["new_verdict"]
    return effective


def _effective_light(pipeline_light: str | None, actions: list[dict]) -> str | None:
    """The traffic light after a human override, or the pipeline light if none has landed.

    Mirrors _effective_verdict's latest-wins rule, then re-derives the light from the human's
    label via the human-review rubric (litmuz_core.severity.human_review_light) rather than the
    pipeline gates: a human decision is a terminal authority the pipeline rubric does not apply
    to (AC-SEVERITY guards like the safety gate only bind the automated verdict).
    """
    light = pipeline_light
    for action in actions:  # ordered oldest to newest
        if action["action"] != "override_verdict" or action["new_verdict"] is None:
            continue
        label = action["new_verdict"].get("label")
        if label:
            light = human_review_light(JudgeLabel(label)).value
    return light


def _review_meta(actions: list[dict]) -> dict:
    """Whether a claim has been resolved by a human, and by whom/when/how.

    "Resolved" means at least one accept or override_verdict action exists; a bare add_note
    never resolves a claim. When more than one terminal action exists (a reviewer accepted,
    then later overrode, for instance), the latest one wins and its reviewer/time/action are
    what is reported, matching _effective_verdict and _effective_light.
    """
    terminal = [a for a in actions if a["action"] in _TERMINAL_REVIEW_ACTIONS]
    if not terminal:
        return {"reviewed": False, "reviewed_by": None, "reviewed_at": None, "review_action": None}
    last = terminal[-1]
    return {
        "reviewed": True,
        "reviewed_by": last["reviewer_identity"],
        "reviewed_at": last["created_at"],
        "review_action": last["action"],
    }


def report_owner(conn, report_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT user_sub FROM reports WHERE report_id = %s", (report_id,))
        row = cur.fetchone()
        return row[0] if row else None


def claim_owner(conn, claim_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.user_sub FROM claims c JOIN reports r ON r.report_id = c.report_id "
            "WHERE c.claim_id = %s",
            (claim_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def list_queue(conn, *, user_sub: str | None = None) -> list[dict[str, Any]]:
    """Flagged claims still awaiting a human decision, with their report id.

    A claim routed to review leaves the queue once it has a terminal reviewer action (accept
    or override_verdict); a bare add_note does not remove it. This is what makes Accept and
    Override actually resolve a claim instead of it reappearing on every read.
    """
    sql = (
        "SELECT c.claim_id, c.report_id, c.text, c.category, c.diagnostic, c.traffic_light "
        "FROM claims c JOIN reports r ON r.report_id = c.report_id "
        "WHERE c.routed_to_review AND NOT EXISTS ("
        "  SELECT 1 FROM reviewer_actions ra "
        "  WHERE ra.claim_id = c.claim_id AND ra.action = ANY(%s)"
        ")"
    )
    params: list = [list(_TERMINAL_REVIEW_ACTIONS)]
    if user_sub is not None:
        sql += " AND r.user_sub = %s"
        params.append(user_sub)
    sql += " ORDER BY c.report_id, c.ordinal"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [
            {**row, "claim_id": str(row["claim_id"]), "report_id": str(row["report_id"])}
            for row in cur.fetchall()
        ]
