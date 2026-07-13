"""Atomic-claim decomposition (FR-1 / AC-DECOMP-1,2,4,5,8,9,10).

The memo body is split off from its reference section (deterministic string work), then
the model is asked to return the body's atomic factual claims as verbatim strings. Each
returned string is located as a verbatim substring so its source span is exact, never
fabricated; identical strings collapse to one claim; and each claim's in-text citation
markers are resolved to concrete identifiers by the deterministic reference layer. What
the body did not turn into a claim is reported as unclaimed spans so a reviewer can see
the gaps.

Two rejections happen before the model is ever touched: a memo over the configured byte
cap, and a degenerate (empty or whitespace-only) memo. Both raise DecomposeError.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..config import Config
from ..llm import LlmClient
from ..prompt_safety import UNTRUSTED_DATA_RULE, wrap_untrusted
from ..schemas import CitedId, Claim, SourceSpan
from .references import build_reference_index, resolve_citations, split_reference_section

_SYSTEM = (
    "You are a claim decomposition engine for scientific drug-discovery memos. "
    "Given the body of a memo, extract its atomic factual claims. Each claim must be a "
    "single, independently checkable assertion copied verbatim from the memo text, "
    "preserving any in-text citation markers. If one sentence carries two independent "
    "assertions, split it into two separate claims. Do not paraphrase, summarize, or "
    "invent text that is not present. Respond with a single JSON array of strings and "
    "nothing else.\n\n" + UNTRUSTED_DATA_RULE
)

_PROMPT_TEMPLATE = "Extract the atomic factual claims from this memo body:\n\n{body}"

# Greedy match of the outermost JSON array in the response text.
_RE_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


class DecomposeError(ValueError):
    """Raised for input that is rejected before any model call."""


@dataclass
class DecomposeResult:
    claims: list[Claim]
    unclaimed_spans: list[SourceSpan]


def decompose(memo: str, llm: LlmClient, config: Config) -> DecomposeResult:
    """Decompose a memo body into atomic claims with exact source spans.

    Rejects (before touching the model) a memo over config.max_input_bytes or a
    degenerate memo, then extracts, locates, deduplicates, and cites each claim.
    """
    if len(memo.encode("utf-8")) > config.max_input_bytes:
        raise DecomposeError("memo exceeds the configured byte cap")
    if not memo.strip():
        raise DecomposeError("memo is empty or whitespace only")

    body, _reference_text = split_reference_section(memo)
    index = build_reference_index(memo)

    response = llm.complete(
        system=_SYSTEM,
        prompt=_PROMPT_TEMPLATE.format(body=wrap_untrusted(body)),
        temperature=0.0,
    )
    claim_texts = _parse_claim_texts(response.text)

    claims: list[Claim] = []
    seen: set[str] = set()
    for text in claim_texts:
        if text in seen:
            continue
        start = body.find(text)
        if start < 0:
            continue
        seen.add(text)
        cited_ids: list[CitedId] = [rc.cited_id for rc in resolve_citations(text, index)]
        ordinal = len(claims)
        claims.append(
            Claim(
                id=f"c{ordinal + 1}",
                ordinal=ordinal,
                text=text,
                source_span=SourceSpan(start=start, end=start + len(text)),
                cited_ids=cited_ids,
                attribution=None,
            )
        )

    unclaimed = _unclaimed_spans(body, [claim.source_span for claim in claims])
    return DecomposeResult(claims=claims, unclaimed_spans=unclaimed)


def _parse_claim_texts(text: str) -> list[str]:
    """Extract the JSON array of claim strings from the model text.

    Returns an empty list when the response holds no usable array; non-string array
    items are ignored so a malformed element never becomes a claim.
    """
    match = _RE_JSON_ARRAY.search(text)
    if match is None:
        return []
    try:
        payload = json.loads(match.group(0))
    except (ValueError, TypeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, str) and item]


def _unclaimed_spans(body: str, spans: list[SourceSpan]) -> list[SourceSpan]:
    """Body ranges not covered by any claim span, with pure-whitespace runs excluded."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted((s.start, s.end) for s in spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    result: list[SourceSpan] = []
    cursor = 0
    for start, end in merged:
        if start > cursor:
            _append_trimmed(result, body, cursor, start)
        cursor = max(cursor, end)
    if cursor < len(body):
        _append_trimmed(result, body, cursor, len(body))
    return result


def _append_trimmed(result: list[SourceSpan], body: str, start: int, end: int) -> None:
    """Append the range [start, end) to result, trimmed of edge whitespace and dropped
    entirely if it is pure whitespace."""
    segment = body[start:end]
    if not segment.strip():
        return
    lead = len(segment) - len(segment.lstrip())
    trail = len(segment) - len(segment.rstrip())
    result.append(SourceSpan(start=start + lead, end=end - trail))
