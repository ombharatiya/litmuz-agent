"""MCP tool implementations as plain, testable functions.

They call the same litmuz_service and litmuz_core as the REST adapter, so an MCP call and a
web submission produce the same result (AC-MCP-3). get_provenance and get_job_status enforce
per-user authorization: a cross-user id is a typed not-found, never another user's data
(AC-MCP-5). Caller-supplied sources are additive evidence that never suppress the deterministic
citation check or the safety cap (AC-MCP-6).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from litmuz_core.cite.identifiers import extract_identifiers
from litmuz_core.config import Config, RetrievalMode
from litmuz_core.pipeline import verify_claim as _core_verify_claim
from litmuz_core.schemas import Passage
from litmuz_service import Queue, submit
from litmuz_store import get_job, read_report, report_owner


class NotFound(Exception):
    """Returned to the caller as a typed not-found (also covers cross-user access)."""


@dataclass
class McpContext:
    app_conn_factory: Callable[[], object]
    api_conn_factory: Callable[[], object]
    queue: Queue
    config: Config = field(default_factory=Config)
    llm: object = None  # used only by the synchronous verify_claim path
    metadata_client: object = None
    retrieval_client: object = None


def verify_output(
    ctx: McpContext, *, principal: str, text: str, sources: list[str] | None = None
) -> dict:
    """Submit a memo and return the job id (async, mirrors POST /verifications).

    sources is reserved: verify_output submits the memo unchanged, so caller sources cannot
    affect the deterministic checks or the safety cap on this path.
    """
    with ctx.app_conn_factory() as conn:
        job_id = submit(
            memo=text, user_sub=principal, app_conn=conn, queue=ctx.queue, config=ctx.config
        )
    return {"job_id": job_id}


def get_job_status(ctx: McpContext, *, principal: str, job_id: str) -> dict:
    with ctx.api_conn_factory() as conn:
        job = get_job(conn, job_id)
        if job is None or job["user_sub"] != principal:
            raise NotFound(f"no such job: {job_id}")
        return {
            "job_id": str(job["job_id"]),
            "status": job["status"],
            "stage": job["stage"],
            "claims_done": job["claims_done"],
            "claims_total": job["claims_total"],
            "report_id": str(job["report_id"]) if job["report_id"] else None,
        }


def get_provenance(ctx: McpContext, *, principal: str, report_id: str) -> dict:
    with ctx.api_conn_factory() as conn:
        owner = report_owner(conn, report_id)
        if owner is None or owner != principal:
            raise NotFound(f"no such report: {report_id}")
        return read_report(conn, report_id).model_dump(mode="json")


def verify_claim(
    ctx: McpContext,
    *,
    principal: str,
    claim: str,
    citation: str | None = None,
    sources: list[str] | None = None,
) -> dict:
    """Synchronous single-claim verdict with the safety marker (AC-JOB-4, AC-MCP-6)."""
    cited_ids = extract_identifiers(citation) if citation else None
    caller_passages = (
        [
            Passage(
                source_id="caller-supplied", text=s, retrieval_mode=RetrievalMode.CALLER_SUPPLIED
            )
            for s in sources
        ]
        if sources
        else None
    )
    result = _core_verify_claim(
        claim,
        cited_ids=cited_ids or None,
        caller_passages=caller_passages,
        llm=ctx.llm,
        metadata_client=ctx.metadata_client,
        retrieval_client=ctx.retrieval_client,
        config=ctx.config,
    )
    return {
        "claim": result.text,
        "category": result.category.value if result.category else None,
        "diagnostic": result.diagnostic.value if result.diagnostic else None,
        "traffic_light": result.traffic_light.value if result.traffic_light else None,
        "verdict": result.verdict.model_dump(mode="json") if result.verdict else None,
        "citation_checks": [c.model_dump(mode="json") for c in result.citation_checks],
        "auto_pass_blocked": result.auto_pass_blocked,
        "requires_human_review": bool(result.routed_to_review),
    }
