"""Session titling: a best-effort, cheap-model name for a memo (never a verdict input)."""

from litmuz_core.config import Config
from litmuz_core.llm import LlmError, LlmResponse
from litmuz_core.title import TITLE_SYSTEM_PROMPT, generate_title


class _FakeLlm:
    def __init__(self, text="", raise_error=False):
        self.text = text
        self.raise_error = raise_error
        self.model = None

    def complete(self, *, system, prompt, temperature=0.0, max_tokens=1024, model=None):
        if self.raise_error:
            raise LlmError("boom")
        self.model = model
        return LlmResponse(text=self.text, model=model or "fake")


def test_generate_title_returns_a_cleaned_single_line():
    llm = _FakeLlm(text='  "TP53 loss and tumour proliferation."  \n')
    title = generate_title("TP53 loss drives proliferation [1].", llm=llm)
    assert title == "TP53 loss and tumour proliferation"


def test_generate_title_uses_the_cheap_title_model():
    llm = _FakeLlm(text="A title")
    generate_title("some memo", llm=llm, config=Config())
    assert llm.model == Config().title_model


def test_generate_title_fences_the_untrusted_memo():
    # The memo is wrapped so the titling call cannot be hijacked, same as the verdict stages.
    assert "untrusted user input" in TITLE_SYSTEM_PROMPT


def test_generate_title_is_best_effort_on_model_failure():
    assert generate_title("memo", llm=_FakeLlm(raise_error=True)) == ""


def test_generate_title_empty_memo_returns_empty():
    assert generate_title("   ", llm=_FakeLlm(text="ignored")) == ""
