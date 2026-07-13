"""Reusable pipeline test doubles and a demo fixture memo.

FakePipelineLlm routes the three pipeline model calls (decomposition, the entailment judge,
categorization) so one fake drives run_pipeline end to end with no model. The metadata and
retrieval fakes resolve a known-good PMID and a fabricated one. Adapter test suites import
these so the doubles live in one place.
"""

from __future__ import annotations

import json

from .cite.clients import Resolution, ResolutionOutcome, SourceRecord
from .config import RetrievalMode, SourceStatus
from .judge.judge import JUDGE_SYSTEM_PROMPT
from .llm import LlmError, LlmResponse
from .retrieve.clients import CitedSource
from .schemas import Passage
from .title import TITLE_SYSTEM_PROMPT

DEMO_MEMO = """\
TP53 loss drives tumour proliferation [1].
The recommended dose was 5 mg daily [1].
A fabricated result was reported [2].

References
1. Smith J, Doe A. A TP53 study in carcinoma. Nature. 2020. PMID: 12345.
2. Ghost Author. A nonexistent work. 2099. PMID: 99999999.
"""

_CLAIMS = [
    "TP53 loss drives tumour proliferation [1].",
    "The recommended dose was 5 mg daily [1].",
    "A fabricated result was reported [2].",
]
_SOURCE_TEXT = "TP53 loss drives proliferation in carcinoma models. More detail followed."
_EVIDENCE = "TP53 loss drives proliferation in carcinoma models."


class FakePipelineLlm:
    """Routes by prompt. judge_mode='raise' makes the judge fail (isolated to judge_error)."""

    def __init__(self, judge_mode: str = "ok") -> None:
        self.judge_calls = 0
        self.judge_mode = judge_mode

    def complete(
        self, *, system, prompt, temperature=0.0, max_tokens=1024, model=None
    ) -> LlmResponse:
        if system == TITLE_SYSTEM_PROMPT:
            return LlmResponse(text="A TP53 study in carcinoma", model="fake")
        if system == JUDGE_SYSTEM_PROMPT:
            self.judge_calls += 1
            if self.judge_mode == "raise":
                raise LlmError("judge boom")
            body = {
                "label": "supported",
                "evidence_sentence": _EVIDENCE,
                "confidence": 0.95,
                "rationale": "the passage states this",
            }
            return LlmResponse(text=json.dumps(body), model="fake")
        if "safety_critical" in (system + prompt).lower():
            return LlmResponse(
                text=json.dumps({"category": "mechanistic", "confidence": 0.99}), model="fake"
            )
        return LlmResponse(text=json.dumps(_CLAIMS), model="fake")


class FakeMetadataClient:
    def __init__(self, raise_error: bool = False) -> None:
        self.raise_error = raise_error

    def resolve(self, cited_id):
        if self.raise_error:
            raise RuntimeError("metadata boom")
        if cited_id.value == "12345":
            record = SourceRecord(
                identifier="pmid:12345",
                surnames=("Smith", "Doe"),
                print_year=2020,
                source_status=SourceStatus.ACTIVE,
            )
            return Resolution(ResolutionOutcome.FOUND, record, "fake")
        return Resolution(ResolutionOutcome.ABSENT, None, "fake")


class FakeRetrievalClient:
    def fetch_cited(self, cited_id):
        if cited_id.value == "12345":
            return CitedSource(
                source_id="pmid:12345", text=_SOURCE_TEXT, is_open_access_fulltext=True
            )
        return None

    def search(self, query, k):
        return [Passage(source_id="s1", text="Unrelated.", retrieval_mode=RetrievalMode.RETRIEVED)]
