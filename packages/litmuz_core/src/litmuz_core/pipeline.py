"""Pipeline orchestration: decompose, check citations, retrieve, judge, categorize,
score severity, and assemble the report (the five stages of the solution overview).

The adapters (REST, worker, MCP) call this one function so every surface produces the
same result. The judge runs only after the deterministic pre-filter: a claim with a
fabricated citation or no usable passage never reaches the model (AC-JUDGE-4, AC-NFR-3).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from .categorize.categorizer import categorize
from .cite.checker import ResolutionCache, check_citation
from .cite.identifiers import extract_identifiers
from .config import Config, ResolutionStatus, RetrievalMode
from .decompose.decomposer import decompose
from .decompose.references import ResolvedCitation, build_reference_index, resolve_citations
from .judge.judge import judge_claim
from .llm import LlmClient
from .report.assembler import assemble_report
from .retrieve.retriever import RetrievalError, retrieve_for_claim
from .schemas import CitedId, Claim, ClaimAttribution, Evidence, Report, SourceSpan
from .severity.mapping import score_claim

ProgressFn = Callable[[str, int, int], None]


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _process_claim(
    claim: Claim,
    resolved: list[ResolvedCitation],
    *,
    llm: LlmClient,
    metadata_client,
    retrieval_client,
    config: Config,
    cache: ResolutionCache,
    passages_override=None,
) -> Claim:
    """Run every per-claim stage for one claim and return the fully scored Claim.

    Shared by run_pipeline and verify_claim so the two surfaces are identical by
    construction (AC-MCP-3). passages_override supplies caller-provided evidence; the
    deterministic citation check still runs and the safety cap still holds (AC-MCP-6).
    """
    checks = [
        check_citation(rc.cited_id, rc.attribution, metadata_client, config, cache)
        for rc in resolved
    ]
    fabricated = any(c.resolution_status is ResolutionStatus.FABRICATED for c in checks)

    if passages_override is not None:
        passages, retrieval_mode = passages_override, RetrievalMode.CALLER_SUPPLIED
    else:
        try:
            passages, retrieval_mode = retrieve_for_claim(claim, retrieval_client, config)
        except RetrievalError:
            # A transient retrieval failure is not a green: fall through to unverifiable.
            passages, retrieval_mode = [], RetrievalMode.NONE

    # Deterministic pre-filter: only invoke the judge when it can add signal.
    if passages and not fabricated:
        verdict, evidence = judge_claim(claim.text, passages, llm, config)
    else:
        verdict, evidence = None, Evidence(evidence_not_located=True)

    category = categorize(claim.text, llm, config)
    severity = score_claim(
        category=category,
        label=verdict.label if verdict else None,
        confidence=verdict.confidence if verdict else None,
        citation_checks=checks,
        retrieval_mode=retrieval_mode,
        claim_text=claim.text,
        config=config,
    )

    return claim.model_copy(
        update={
            "cited_ids": [rc.cited_id for rc in resolved],
            "citation_checks": checks,
            "retrieval_mode": retrieval_mode,
            "verdict": verdict,
            "evidence": evidence,
            "category": category,
            "diagnostic": severity.diagnostic,
            "traffic_light": severity.traffic_light,
            "auto_pass_blocked": severity.auto_pass_blocked,
            "auto_passed": severity.auto_passed,
            "routed_to_review": severity.routed_to_review,
            "effective_verdict": verdict,
        }
    )


def run_pipeline(
    memo: str,
    *,
    llm: LlmClient,
    metadata_client,
    retrieval_client,
    config: Config | None = None,
    report_id: str = "report",
    job_id: str = "job",
    created_at: str | None = None,
    on_progress: ProgressFn | None = None,
) -> Report:
    config = config or Config()
    created_at = created_at or _now_iso()

    def progress(stage: str, done: int, total: int) -> None:
        if on_progress is not None:
            on_progress(stage, done, total)

    progress("decompose", 0, 1)
    decomposed = decompose(memo, llm, config)
    index = build_reference_index(memo)
    cache: ResolutionCache = {}
    total = len(decomposed.claims)
    progress("decompose", 1, 1)

    final_claims: list[Claim] = []
    for i, claim in enumerate(decomposed.claims):
        resolved = resolve_citations(claim.text, index)
        final_claims.append(
            _process_claim(
                claim,
                resolved,
                llm=llm,
                metadata_client=metadata_client,
                retrieval_client=retrieval_client,
                config=config,
                cache=cache,
            )
        )
        progress("verify", i + 1, total)

    return assemble_report(
        report_id=report_id,
        job_id=job_id,
        memo_hash=hashlib.sha256(memo.encode("utf-8")).hexdigest(),
        claims=final_claims,
        unclaimed_spans=decomposed.unclaimed_spans,
        model_versions={"judge": config.judge_model},
        rubric_version="1",
        created_at=created_at,
    )


def verify_claim(
    claim_text: str,
    *,
    cited_ids: list[CitedId] | None = None,
    attribution: ClaimAttribution | None = None,
    caller_passages=None,
    llm: LlmClient,
    metadata_client,
    retrieval_client=None,
    config: Config | None = None,
) -> Claim:
    """Verify a single claim synchronously (AC-JOB-4). No decomposition, queue or database.

    cited_ids/attribution come from the caller (for example an MCP citation argument); if
    omitted, inline identifiers in the claim text are used. caller_passages are caller-supplied
    evidence that never suppress the deterministic citation check or the safety cap (AC-MCP-6).
    """
    config = config or Config()
    if cited_ids is None:
        cited_ids = extract_identifiers(claim_text)
    resolved = [
        ResolvedCitation(cited_id=cid, attribution=attribution or ClaimAttribution())
        for cid in cited_ids
    ]
    claim = Claim(
        id="c1",
        ordinal=0,
        text=claim_text,
        source_span=SourceSpan(start=0, end=len(claim_text)),
        cited_ids=cited_ids,
    )
    return _process_claim(
        claim,
        resolved,
        llm=llm,
        metadata_client=metadata_client,
        retrieval_client=retrieval_client,
        config=config,
        cache={},
        passages_override=caller_passages,
    )
