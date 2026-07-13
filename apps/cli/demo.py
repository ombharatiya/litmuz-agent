"""Scripted, offline demo of the Litmuz verification layer.

Runs fixed memos through the real pipeline with deterministic test doubles (no network, no
model), and narrates the four beats the platform is built to guarantee:

  1. A fabricated citation is caught deterministically and forced red, whatever a judge says.
  2. A mechanistic claim whose support is not located is held yellow, not a pass; the judge
     is never asked to invent support.
  3. A safety-critical claim (a dose) can never auto-pass; it is capped and routed to review.
  4. The judge model is one config value; swapping it changes the report provenance, no code.

Run it:
  uv run python apps/cli/demo.py

The same assertions run in the test suite (packages/litmuz_core/tests/test_demo_script.py),
so the demo cannot drift from the guarantees it claims.
"""

from __future__ import annotations

import dataclasses
import json

from litmuz_core.config import Category, Config, Diagnostic, RetrievalMode, TrafficLight
from litmuz_core.judge.judge import JUDGE_SYSTEM_PROMPT
from litmuz_core.llm import LlmResponse
from litmuz_core.pipeline import run_pipeline
from litmuz_core.schemas import Report
from litmuz_core.testing import (
    DEMO_MEMO,
    FakeMetadataClient,
    FakePipelineLlm,
    FakeRetrievalClient,
)

# A single-claim memo whose mechanism has no locatable support. Kept local so the shared
# DEMO_MEMO (asserted by the adapter suites) is untouched.
YELLOW_MEMO = "The proposed mechanism is not present in any retrieved passage.\n"


class _NoSupportLlm:
    """Decomposes the yellow memo and categorizes it mechanistic; the judge must never run."""

    def complete(self, *, system, prompt, temperature=0.0, max_tokens=1024) -> LlmResponse:
        if system == JUDGE_SYSTEM_PROMPT:
            raise AssertionError("the judge must not run when no passage is located")
        if "safety_critical" in (system + prompt).lower():
            return LlmResponse(
                text=json.dumps({"category": "mechanistic", "confidence": 0.99}), model="fake"
            )
        return LlmResponse(text=json.dumps([YELLOW_MEMO.strip()]), model="fake")


class _EmptyRetrieval:
    """Nothing is fetchable or searchable, so retrieval resolves to none (not a fabrication)."""

    def fetch_cited(self, cited_id):
        return None

    def search(self, query, k):
        return []


def run_demo(judge_model: str | None = None) -> Report:
    """Verify the demo memo end to end with fakes. Optionally override the judge model."""
    config = Config()
    if judge_model is not None:
        config = dataclasses.replace(config, judge_model=judge_model)
    return run_pipeline(
        DEMO_MEMO,
        llm=FakePipelineLlm(),
        metadata_client=FakeMetadataClient(),
        retrieval_client=FakeRetrievalClient(),
        config=config,
    )


def run_yellow_scenario() -> Report:
    """Verify the not-located memo end to end; the judge fake raises if it is called."""
    return run_pipeline(
        YELLOW_MEMO,
        llm=_NoSupportLlm(),
        metadata_client=FakeMetadataClient(),
        retrieval_client=_EmptyRetrieval(),
        config=Config(),
    )


def _claim(report: Report, needle: str):
    for claim in report.claims:
        if needle in claim.text:
            return claim
    raise AssertionError(f"no claim containing {needle!r}")


def _check(label: str, ok: bool) -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    return ok


def narrate(report: Report, yellow: Report) -> bool:
    ok = True

    print("Beat 1 - a fabricated citation is caught and forced red")
    fabricated = _claim(report, "fabricated result")
    statuses = [c.resolution_status.value for c in fabricated.citation_checks]
    ok &= _check(f"citation resolves as fabricated (got {statuses})", "fabricated" in statuses)
    ok &= _check("traffic light is red", fabricated.traffic_light == TrafficLight.RED)
    ok &= _check("not auto-passed", fabricated.auto_passed is not True)

    print("\nBeat 2 - unlocated mechanistic support is held yellow, never a pass")
    unresolved = yellow.claims[0]
    ok &= _check("mechanistic category", unresolved.category == Category.MECHANISTIC)
    ok &= _check("traffic light is yellow", unresolved.traffic_light == TrafficLight.YELLOW)
    ok &= _check("diagnostic is D3 (unverifiable)", unresolved.diagnostic == Diagnostic.D3)
    ok &= _check("no support was fabricated", unresolved.retrieval_mode == RetrievalMode.NONE)
    ok &= _check("routed to human review", unresolved.routed_to_review is True)

    print("\nBeat 3 - a safety-critical claim can never auto-pass")
    dose = _claim(report, "5 mg")
    ok &= _check("categorized safety_critical", dose.category == Category.SAFETY_CRITICAL)
    ok &= _check("not green", dose.traffic_light != TrafficLight.GREEN)
    ok &= _check("not auto-passed", dose.auto_passed is not True)
    ok &= _check("routed to human review", dose.routed_to_review is True)

    safety_autopassed = sum(
        1 for c in report.claims if c.category == Category.SAFETY_CRITICAL and c.auto_passed is True
    )
    ok &= _check(
        f"safety-critical auto_passed count == 0 (got {safety_autopassed})",
        safety_autopassed == 0,
    )

    return ok


def demo_model_swap() -> bool:
    print("\nBeat 4 - the judge model is one config value")
    default = run_demo()
    swapped = run_demo(judge_model="claude-sonnet-5")
    default_model = default.model_versions.get("judge")
    swapped_model = swapped.model_versions.get("judge")
    print(f"  default judge model: {default_model}")
    print(f"  swapped judge model: {swapped_model}")
    ok = _check("report provenance reflects the active model", swapped_model == "claude-sonnet-5")
    ok &= _check("no code change, only config", default_model != swapped_model)
    return ok


def main(argv: list[str] | None = None) -> int:
    print("Litmuz demo: deterministic doubles, no network.\n")
    report = run_demo()
    yellow = run_yellow_scenario()
    print(f"Demo memo: {len(report.claims)} claims. Summary: {report.summary_counts}\n")

    ok = narrate(report, yellow)
    ok &= demo_model_swap()

    print()
    if ok:
        print("All four beats held.")
        return 0
    print("A beat did not hold. See the FAIL lines above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
