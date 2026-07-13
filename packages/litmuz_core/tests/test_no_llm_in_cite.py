"""Phase-1 exit guard: the deterministic layer provably contains no LLM.

The product's trust story depends on citation/retraction checks that never touch a
model (AC-JUDGE-4, AC-NFR-3, PRD §8). This test fails the build if an LLM SDK or the
judge module ever leaks into the citation layer.
"""

import pathlib
import re
import sys

from litmuz_core import cite  # noqa: F401  (import under test)

CITE_DIR = pathlib.Path(cite.__file__).parent
REFERENCES = pathlib.Path(cite.__file__).parents[1] / "decompose" / "references.py"

_FORBIDDEN_IMPORT = re.compile(
    r"(?m)^\s*(?:import|from)\s+(anthropic|openai|litmuz_core\.judge|\.\.judge|\.judge)\b"
)
_FORBIDDEN_TOKENS = ("anthropic", "openai")


def _sources() -> dict[pathlib.Path, str]:
    files = sorted(CITE_DIR.glob("*.py")) + [REFERENCES]
    return {f: f.read_text() for f in files}


def test_no_llm_or_judge_imports_in_deterministic_layer():
    for path, src in _sources().items():
        assert not _FORBIDDEN_IMPORT.search(src), f"LLM/judge import found in {path.name}"
        low = src.lower()
        for token in _FORBIDDEN_TOKENS:
            assert token not in low, f"'{token}' appears in {path.name}"


def test_importing_the_citation_layer_pulls_in_no_llm_sdk():
    assert "anthropic" not in sys.modules
    assert "openai" not in sys.modules
