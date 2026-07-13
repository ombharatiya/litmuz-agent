"""Pipeline orchestration: decompose, check citations, retrieve, judge, categorize,
score severity, and assemble the report (the five stages of the solution overview).

The adapters (REST, worker, MCP) call this one function so every surface produces the
same result. The judge runs only after the deterministic pre-filter: a claim with a
fabricated citation or no usable passage never reaches the model (AC-JUDGE-4, AC-NFR-3).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable

from .categorize.categorizer import categorize
from .cite.checker import ResolutionCache, check_citation
from .cite.identifiers import extract_identifiers
from .config import Category, Config, ResolutionStatus, RetrievalMode, VerificationMode
from .decompose.decomposer import decompose
from .decompose.references import (
    ResolvedCitation,
    build_reference_index,
    resolve_citations,
    split_reference_section,
)
from .genomic import check_genomic_claim
from .judge.judge import judge_claim
from .llm import LlmClient
from .report.assembler import assemble_report
from .retrieve.retriever import RetrievalError, retrieve_for_claim
from .schemas import CitedId, Claim, ClaimAttribution, Evidence, Report, SourceSpan, Verdict
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


def _process_genomic_claim(claim: Claim, *, config: Config) -> Claim:
    """Score one claim against the genomic reference (Human Accelerated Regions + Zoonomia).

    Deterministic: no citation registries, no retrieval, no judge. The genomic check yields a
    verdict and evidence, which the shared severity mapping (score_claim) turns into a diagnostic,
    traffic light, and routing exactly as in the literature path - so the safety gate and the
    honest-negative guarantees still hold (an unverifiable claim is a yellow, never a green).
    """
    result = check_genomic_claim(claim.text)
    verdict = (
        Verdict(label=result.label, confidence=result.confidence, rationale=result.rationale)
        if result.label is not None
        else None
    )
    severity = score_claim(
        category=Category.MECHANISTIC,
        label=result.label,
        confidence=result.confidence,
        citation_checks=[],
        retrieval_mode=result.retrieval_mode,
        claim_text=claim.text,
        config=config,
    )
    return claim.model_copy(
        update={
            "cited_ids": [],
            "citation_checks": [],
            "retrieval_mode": result.retrieval_mode,
            "verdict": verdict,
            "evidence": result.evidence,
            "category": Category.MECHANISTIC,
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
    mode: VerificationMode = VerificationMode.LITERATURE,
) -> Report:
    config = config or Config()
    created_at = created_at or _now_iso()

    def progress(stage: str, done: int, total: int) -> None:
        if on_progress is not None:
            on_progress(stage, done, total)

    genomic = mode is VerificationMode.GENOMIC

    progress("decompose", 0, 1)
    if genomic:
        # Genomic mode is fully deterministic: split the body into sentence-claims directly rather
        # than through the LLM decomposer, whose drug-discovery framing drops evolutionary-genomics
        # statements. No model, no variance - every sentence becomes a checkable claim.
        claims_in = _split_genomic_claims(memo)
        unclaimed: list[SourceSpan] = []
        index = {}
    else:
        decomposed = decompose(memo, llm, config)
        claims_in = decomposed.claims
        unclaimed = decomposed.unclaimed_spans
        index = build_reference_index(memo)
    cache: ResolutionCache = {}
    total = len(claims_in)
    progress("decompose", 1, 1)

    final_claims: list[Claim] = []
    for i, claim in enumerate(claims_in):
        if genomic:
            final_claims.append(_process_genomic_claim(claim, config=config))
        else:
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

    model_versions = (
        {"genomic_reference": "gladstone-har-zoonomia"}
        if genomic
        else {"judge": config.judge_model}
    )
    return assemble_report(
        report_id=report_id,
        job_id=job_id,
        memo_hash=hashlib.sha256(memo.encode("utf-8")).hexdigest(),
        claims=final_claims,
        unclaimed_spans=unclaimed,
        model_versions=model_versions,
        rubric_version="1",
        created_at=created_at,
    )


def _split_genomic_claims(memo: str) -> list[Claim]:
    """Deterministically split a genomic memo body into one claim per sentence, with exact spans.

    Sentences end at . ? or ! (or a line break); the reference section is stripped first. Verbatim
    text and offsets are preserved so a claim always locates back to the memo.
    """
    body, _ = split_reference_section(memo)
    claims: list[Claim] = []
    for piece in re.finditer(r"[^.?!\n]*[.?!]|[^.?!\n]*\S", body):
        raw = piece.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        lead = len(raw) - len(raw.lstrip())
        start = piece.start() + lead
        ordinal = len(claims)
        claims.append(
            Claim(
                id=f"c{ordinal + 1}",
                ordinal=ordinal,
                text=stripped,
                source_span=SourceSpan(start=start, end=start + len(stripped)),
                cited_ids=[],
                attribution=None,
            )
        )
    return claims


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
