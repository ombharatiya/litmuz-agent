"""FastAPI REST adapter. Contains no verification logic: it validates, enqueues, reads the
store, and serves the review queue, calling litmuz_service and litmuz_store.

Auth is dark-shippable: with no verifier configured the app runs open and keys everything to
a default principal (AC-AUTH-3); with a verifier, a missing or invalid bearer token is 401
and a cross-user access is 403 (AC-API-3, AC-AUTH-2).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from litmuz_core.config import Config
from litmuz_core.report.assembler import human_readable
from litmuz_service import EmptyMemo, Queue, QuotaExceeded, SubmissionTooLarge, submit, usage_for
from litmuz_store import (
    add_reviewer_action,
    claim_owner,
    get_job,
    list_jobs,
    list_queue,
    read_report,
    report_owner,
)

DEFAULT_PRINCIPAL = "anonymous"
_ACTIONS = {"accept", "override_verdict", "add_note"}
# A human's final verdict label. judge_error is a machine-only outcome (a passage that
# exhausted retries), never something a reviewer asserts, so it is excluded here.
_REVIEW_LABELS = {"supported", "contradicted", "unsupported"}


class InvalidToken(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str) -> str:
        """Return the principal (sub) for a valid token, or raise InvalidToken."""
        ...


@dataclass
class ApiContext:
    app_conn_factory: Callable[[], object]  # a litmuz_app connection
    api_conn_factory: Callable[[], object]  # a litmuz_api connection
    queue: Queue
    config: Config = field(default_factory=Config)
    verifier: TokenVerifier | None = None  # None => dark-ship (open, default principal)
    cors_origins: list[str] = field(default_factory=list)


class SubmitBody(BaseModel):
    text: str


class ReviewBody(BaseModel):
    action: str
    note: str = ""
    new_verdict: dict | None = None


def create_app(ctx: ApiContext) -> FastAPI:
    app = FastAPI(title="Litmuz API", version="0.0.0")
    if ctx.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=ctx.cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["authorization", "content-type"],
        )

    def principal(request: Request) -> str:
        if ctx.verifier is None:
            return DEFAULT_PRINCIPAL
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        try:
            return ctx.verifier.verify(auth[7:].strip())
        except InvalidToken:
            raise HTTPException(status_code=401, detail="invalid token") from None

    def _authorize(who: str, owner: str) -> None:
        if ctx.verifier is not None and who != owner:
            raise HTTPException(status_code=403, detail="forbidden")

    def _tier(request: Request) -> str | None:
        # The billing tier for the quota. None (unlimited) when auth is dark-shipped, or when
        # the verifier does not expose tiers (the test double). Otherwise read from the token.
        if ctx.verifier is None:
            return None
        tier_fn = getattr(ctx.verifier, "tier", None)
        if tier_fn is None:
            return None
        auth = request.headers.get("authorization", "")
        return tier_fn(auth[7:].strip())

    @app.get("/health")
    def health() -> dict:
        # Public uptime probe (the gateway exposes this route without the authorizer).
        # Deliberately touches nothing: no DB, no queue.
        return {"status": "ok"}

    @app.post("/verifications", status_code=202)
    def create_verification(
        body: SubmitBody, request: Request, who: str = Depends(principal)
    ) -> dict:
        with ctx.app_conn_factory() as conn:
            try:
                job_id = submit(
                    memo=body.text,
                    user_sub=who,
                    app_conn=conn,
                    queue=ctx.queue,
                    config=ctx.config,
                    tier=_tier(request),
                )
            except SubmissionTooLarge as exc:
                raise HTTPException(status_code=413, detail=str(exc)) from None
            except EmptyMemo as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
            except QuotaExceeded as exc:
                # 402 Payment Required: the weekly allowance is spent. The usage detail drives
                # the upgrade prompt.
                raise HTTPException(status_code=402, detail=exc.usage) from None
        return {"job_id": job_id}

    @app.get("/me/usage")
    def my_usage(request: Request, who: str = Depends(principal)) -> dict:
        tier = _tier(request) or "free"
        with ctx.app_conn_factory() as conn:
            return usage_for(conn, user_sub=who, tier=tier, config=ctx.config)

    @app.get("/me/jobs")
    def my_jobs(who: str = Depends(principal)) -> list:
        # The caller's own sessions, newest first, for the studio view. litmuz_api reads.
        with ctx.api_conn_factory() as conn:
            return list_jobs(conn, who)

    @app.get("/verifications/{job_id}")
    def get_verification(job_id: str, who: str = Depends(principal)) -> dict:
        with ctx.api_conn_factory() as conn:
            job = get_job(conn, job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="job not found")
            _authorize(who, job["user_sub"])
            return {
                "job_id": str(job["job_id"]),
                "status": job["status"],
                "stage": job["stage"],
                "claims_done": job["claims_done"],
                "claims_total": job["claims_total"],
                "report_id": str(job["report_id"]) if job["report_id"] else None,
                # The full memo and title let the studio show a past session's input alongside
                # its report, so an older session is not an empty composer.
                "memo": job.get("memo", ""),
                "title": job.get("title", "") or "",
            }

    @app.get("/reports/{report_id}")
    def get_report(report_id: str, who: str = Depends(principal)) -> dict:
        with ctx.api_conn_factory() as conn:
            owner = report_owner(conn, report_id)
            if owner is None:
                raise HTTPException(status_code=404, detail="report not found")
            _authorize(who, owner)
            return read_report(conn, report_id).model_dump(mode="json")

    @app.get("/reports/{report_id}/export")
    def export_report(report_id: str, who: str = Depends(principal)) -> Response:
        with ctx.api_conn_factory() as conn:
            owner = report_owner(conn, report_id)
            if owner is None:
                raise HTTPException(status_code=404, detail="report not found")
            _authorize(who, owner)
            markdown = human_readable(read_report(conn, report_id))
        return Response(content=markdown, media_type="text/markdown")

    @app.get("/queue")
    def get_queue(who: str = Depends(principal)) -> list:
        with ctx.api_conn_factory() as conn:
            return list_queue(conn, user_sub=who)

    @app.post("/queue/{claim_id}/review", status_code=204)
    def review(claim_id: str, body: ReviewBody, who: str = Depends(principal)) -> Response:
        if body.action not in _ACTIONS:
            raise HTTPException(status_code=400, detail=f"invalid action: {body.action}")
        if body.action == "override_verdict":
            label = (body.new_verdict or {}).get("label")
            if label not in _REVIEW_LABELS:
                allowed = sorted(_REVIEW_LABELS)
                raise HTTPException(
                    status_code=400,
                    detail=f"override_verdict requires new_verdict.label in {allowed}",
                )
            if not (body.new_verdict or {}).get("rationale"):
                raise HTTPException(
                    status_code=400, detail="override_verdict requires new_verdict.rationale"
                )
        with ctx.api_conn_factory() as conn:
            owner = claim_owner(conn, claim_id)
            if owner is None:
                raise HTTPException(status_code=404, detail="claim not found")
            _authorize(who, owner)
            add_reviewer_action(
                conn,
                claim_id,
                reviewer_identity=who,
                action=body.action,
                note=body.note,
                new_verdict=body.new_verdict,
            )
        return Response(status_code=204)

    return app
