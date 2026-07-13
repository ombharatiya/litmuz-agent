"""End-to-end pipeline integration with injected fakes (no network, no model).

Demonstrates the demo behaviours: a supported cited claim grounds and can auto-pass, a
dosing claim is held for a human even when supported, and a fabricated citation is flagged
red without ever reaching the judge (the deterministic pre-filter).
"""

import json

from litmuz_core.config import Category, RetrievalMode, TrafficLight
from litmuz_core.judge.judge import JUDGE_SYSTEM_PROMPT
from litmuz_core.llm import LlmResponse
from litmuz_core.pipeline import run_pipeline
from litmuz_core.report.assembler import human_readable
from litmuz_core.retrieve.clients import CitedSource
from litmuz_core.schemas import Passage

MEMO = """\
TP53 loss drives tumour proliferation [1].
The recommended dose was 5 mg daily [1].
A fabricated result was reported [2].

References
1. Smith J, Doe A. A TP53 study in carcinoma. Nature. 2020. PMID: 12345.
2. Ghost Author. A nonexistent work. 2099. PMID: 99999999.
"""

CLAIMS = [
    "TP53 loss drives tumour proliferation [1].",
    "The recommended dose was 5 mg daily [1].",
    "A fabricated result was reported [2].",
]
SOURCE_TEXT = "TP53 loss drives proliferation in carcinoma models. More detail followed."
EVIDENCE = "TP53 loss drives proliferation in carcinoma models."


class FakeLlm:
    """Routes by prompt: the judge system prompt is exact, the categorizer prompt names the
    categories, and everything else is the decomposition call."""

    def __init__(self) -> None:
        self.judge_calls = 0

    def complete(self, *, system, prompt, temperature=0.0, max_tokens=1024) -> LlmResponse:
        if system == JUDGE_SYSTEM_PROMPT:
            self.judge_calls += 1
            body = {
                "label": "supported",
                "evidence_sentence": EVIDENCE,
                "confidence": 0.95,
                "rationale": "the passage states this",
            }
            return LlmResponse(text=json.dumps(body), model="fake")
        if "safety_critical" in (system + prompt).lower():
            body = {"category": "mechanistic", "confidence": 0.99}
            return LlmResponse(text=json.dumps(body), model="fake")
        return LlmResponse(text=json.dumps(CLAIMS), model="fake")


class FakeRetrieval:
    def fetch_cited(self, cited_id):
        if cited_id.value == "12345":
            return CitedSource(
                source_id="pmid:12345", text=SOURCE_TEXT, is_open_access_fulltext=True
            )
        return None

    def search(self, query, k):
        return [
            Passage(
                source_id="search:1",
                text="Unrelated candidate.",
                retrieval_mode=RetrievalMode.RETRIEVED,
            )
        ]


def _by(claims, needle):
    return next(c for c in claims if needle in c.text)


def test_pipeline_produces_a_grounded_report(fake_client):
    llm = FakeLlm()
    report = run_pipeline(
        MEMO,
        llm=llm,
        metadata_client=fake_client,
        retrieval_client=FakeRetrieval(),
        report_id="r1",
        job_id="j1",
        created_at="2026-07-03T00:00:00Z",
    )

    assert len(report.claims) == 3
    assert report.summary_counts["total"] == 3

    grounded = _by(report.claims, "TP53 loss drives tumour")
    assert grounded.traffic_light is TrafficLight.GREEN
    assert grounded.category is Category.MECHANISTIC
    assert grounded.auto_passed is True

    dosing = _by(report.claims, "recommended dose")
    assert dosing.category is Category.SAFETY_CRITICAL
    assert dosing.traffic_light is not TrafficLight.GREEN
    assert dosing.auto_passed is False
    assert dosing.routed_to_review is True

    fabricated = _by(report.claims, "fabricated result")
    assert fabricated.traffic_light is TrafficLight.RED
    assert fabricated.verdict is None  # the judge was never called for it

    # AC-NFR-3: the judge ran only on the two non-fabricated claims.
    assert llm.judge_calls == 2

    assert human_readable(report).startswith("# Litmuz report r1")
