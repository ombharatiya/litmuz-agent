"""Assemble the provenance report and its human-readable rendering (FR-7, AC-REPORT-*).

The report is the audit artifact: every claim carries its verdict, evidence, citation
state and severity. The human-readable rendering states each verdict in one line and never
dresses an unverifiable or unsupported claim in success wording.
"""

from __future__ import annotations

from collections import Counter

from ..schemas import Claim, Report, SourceSpan

_LIGHT_WORD = {"green": "grounded", "yellow": "needs review", "red": "flagged"}


def summary_counts(claims: list[Claim]) -> dict:
    by_light: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    routed = 0
    for claim in claims:
        if claim.traffic_light is not None:
            by_light[claim.traffic_light.value] += 1
        if claim.category is not None:
            by_category[claim.category.value] += 1
        if claim.routed_to_review:
            routed += 1
    return {
        "total": len(claims),
        "by_traffic_light": dict(by_light),
        "by_category": dict(by_category),
        "routed_to_review": routed,
    }


def assemble_report(
    *,
    report_id: str,
    job_id: str,
    memo_hash: str,
    claims: list[Claim],
    unclaimed_spans: list[SourceSpan],
    model_versions: dict,
    rubric_version: str,
    created_at: str,
) -> Report:
    return Report(
        id=report_id,
        job_id=job_id,
        memo_hash=memo_hash,
        model_versions=model_versions,
        rubric_version=rubric_version,
        summary_counts=summary_counts(claims),
        unclaimed_spans=unclaimed_spans,
        claims=claims,
        created_at=created_at,
    )


def human_readable(report: Report) -> str:
    counts = report.summary_counts
    lines = [
        f"# Litmuz report {report.id}",
        "",
        f"Claims: {counts.get('total', 0)}. Routed to review: {counts.get('routed_to_review', 0)}.",
        f"By traffic light: {counts.get('by_traffic_light', {})}.",
        "",
        "## Claims",
    ]
    for claim in report.claims:
        light = claim.traffic_light.value if claim.traffic_light else "pending"
        word = _LIGHT_WORD.get(light, light)
        verdict = claim.verdict.label.value if claim.verdict else "no judge"
        diagnostic = claim.diagnostic.value if claim.diagnostic else "n/a"
        why = f"verdict {verdict} ({diagnostic})"
        if claim.routed_to_review:
            why += ", routed to human review"
        lines.append(f"- [{light}: {word}] {claim.text}")
        lines.append(f"  {why}.")
    return "\n".join(lines)
