"""Shared Phase 2 contracts: the Passage model and the LLM client protocol.

The LLM module must import with no model SDK installed (lazy construction), mirroring the
citation layer, so unit tests inject a fake and never call a model.
"""

import sys

from litmuz_core.config import RetrievalMode
from litmuz_core.llm import LlmClient, LlmResponse
from litmuz_core.schemas import Passage


def test_passage_model():
    p = Passage(
        source_id="pmid:12345",
        text="p53 induces apoptosis in response to DNA damage.",
        section="results",
        retrieval_mode=RetrievalMode.CITED_FULLTEXT,
    )
    assert p.retrieval_mode is RetrievalMode.CITED_FULLTEXT


def test_llm_module_imports_without_sdk():
    assert "anthropic" not in sys.modules
    assert LlmResponse(text="x", model="m").text == "x"


class _FakeLlm:
    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, *, system, prompt, temperature=0.0, max_tokens=1024) -> LlmResponse:
        return LlmResponse(text=self.text, model="fake")


def test_fake_llm_satisfies_protocol():
    client: LlmClient = _FakeLlm("hello")
    assert client.complete(system="s", prompt="p").text == "hello"
