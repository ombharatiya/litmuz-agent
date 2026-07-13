"""Name a session from its memo, using a small model.

This is a convenience only: the title makes a session identifiable in the studio list. It
never influences a verdict, so it runs off the cheap `title_model`, is best-effort (any model
failure yields an empty string and the caller falls back to a memo snippet), and it treats the
memo as untrusted input with the same structural fence as the verdict stages.
"""

from __future__ import annotations

from .config import Config
from .llm import LlmClient, LlmError
from .prompt_safety import UNTRUSTED_DATA_RULE, wrap_untrusted

TITLE_SYSTEM_PROMPT = (
    "You name a research memo so a user can recognise it in a list. Read the memo and return a "
    "short, specific title of at most 8 words that captures its subject. Return only the title "
    "text, with no quotes, punctuation at the end, label, or explanation. " + UNTRUSTED_DATA_RULE
)

# Only the opening of the memo is needed to name it, and it keeps the cheap call small.
_MEMO_HEAD_CHARS = 1_000
_MAX_TITLE_CHARS = 80


def _clean(raw: str) -> str:
    """Collapse to a single line, strip wrapping quotes, and bound the length."""
    single = " ".join(raw.split())
    if len(single) >= 2 and single[0] in "\"'" and single[-1] == single[0]:
        single = single[1:-1].strip()
    return single[:_MAX_TITLE_CHARS].rstrip(" .,-")


def generate_title(memo: str, *, llm: LlmClient, config: Config | None = None) -> str:
    """Return a short title for the memo, or "" if it cannot be produced.

    Never raises: titling is optional and must never fail a verification job.
    """
    config = config or Config()
    head = memo.strip()[:_MEMO_HEAD_CHARS]
    if not head:
        return ""
    try:
        response = llm.complete(
            system=TITLE_SYSTEM_PROMPT,
            prompt=wrap_untrusted(head),
            model=config.title_model,
            max_tokens=32,
        )
    except LlmError:
        return ""
    return _clean(response.text)
