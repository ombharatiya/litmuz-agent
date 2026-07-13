"""Evidence retrieval orchestration (AC-RETRIEVE-1..8).

Given a claim, decide where its evidence comes from and return ranked passages plus the
``RetrievalMode`` that describes their provenance:

* cited full text (open access) -> verbatim chunks, mode CITED_FULLTEXT (every chunk kept,
  so a supporting sentence outside the first chunk is never lost, AC-RETRIEVE-8);
* cited abstract only -> verbatim abstract passages, mode CITED_ABSTRACT;
* no citation (or the citation was not found) -> a keyword search, mode RETRIEVED;
* nothing usable -> ([], NONE).

A transient upstream failure is retried a bounded number of times and then raised as
``RetrievalError``. It is never quietly collapsed into NONE: not-found and undetermined are
different states (AC-RETRIEVE-6).
"""

from __future__ import annotations

import re
import time

from ..config import Config, RetrievalMode
from ..schemas import Claim, Passage
from .clients import CitedSource, RetrievalClient, RetrievalTransient

_TOKEN = re.compile(r"\S+")

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "than",
        "that",
        "the",
        "then",
        "these",
        "this",
        "those",
        "to",
        "was",
        "were",
        "which",
        "with",
        "we",
    }
)

# Stub gene/drug synonym map so the query-expansion design is present. A curated lexicon
# replaces this later; the shape (surface form -> alternates) stays the same.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "tp53": ("p53",),
    "p53": ("tp53",),
    "egfr": ("her1", "erbb1"),
    "acetaminophen": ("paracetamol", "apap"),
    "paracetamol": ("acetaminophen",),
    "aspirin": ("acetylsalicylic",),
}


class RetrievalError(Exception):
    """Transient upstream failure after the bounded retries were exhausted.

    Distinct from a not-found result. The caller must not treat this as RetrievalMode.NONE.
    """


def retrieve_for_claim(
    claim: Claim, client: RetrievalClient, config: Config
) -> tuple[list[Passage], RetrievalMode]:
    if claim.cited_ids:
        source = _call(lambda: client.fetch_cited(claim.cited_ids[0]), config)
        if source is not None:
            return _passages_from_source(source, config)

    # Uncited, or cited but not found: fall back to a ranked keyword search.
    query = build_query(claim.text)
    passages = _call(lambda: client.search(query, config.top_k), config)
    if passages:
        return passages, RetrievalMode.RETRIEVED  # order preserved from the client
    return [], RetrievalMode.NONE


def build_query(text: str) -> str:
    """Light keyword extraction plus a stub synonym expansion (AC-RETRIEVE-2)."""
    keywords: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-z0-9][a-z0-9-]*", text.lower()):
        if len(token) < 2 or token in _STOPWORDS:
            continue
        if token not in seen:
            seen.add(token)
            keywords.append(token)
        for synonym in _SYNONYMS.get(token, ()):
            if synonym not in seen:
                seen.add(synonym)
                keywords.append(synonym)
    return " ".join(keywords)


def _passages_from_source(
    source: CitedSource, config: Config
) -> tuple[list[Passage], RetrievalMode]:
    mode = (
        RetrievalMode.CITED_FULLTEXT
        if source.is_open_access_fulltext
        else RetrievalMode.CITED_ABSTRACT
    )
    passages = [
        Passage(source_id=source.source_id, text=text, offset=offset, retrieval_mode=mode)
        for text, offset in _chunk(source.text, config.max_passage_tokens)
    ]
    return passages, mode


def _chunk(text: str, max_tokens: int) -> list[tuple[str, int]]:
    """Split ``text`` into chunks of at most ``max_tokens`` whitespace tokens.

    Each chunk is sliced from the original string by character offsets, so every chunk is a
    verbatim substring of ``text`` (no paraphrase, internal whitespace preserved).
    """
    matches = list(_TOKEN.finditer(text))
    if not matches:
        return []
    size = max(1, max_tokens)
    chunks: list[tuple[str, int]] = []
    for i in range(0, len(matches), size):
        group = matches[i : i + size]
        start = group[0].start()
        end = group[-1].end()
        chunks.append((text[start:end], start))
    return chunks


def _call(action, config: Config):
    """Run ``action``, retrying a transient failure a bounded number of times.

    Exhausting the retries raises RetrievalError; it is never mapped to a not-found result.
    """
    attempts = max(1, config.retrieval_max_retries)
    last: RetrievalTransient | None = None
    for attempt in range(attempts):
        try:
            return action()
        except RetrievalTransient as exc:
            last = exc
            if config.retrieval_base_delay_s > 0 and attempt < attempts - 1:
                time.sleep(config.retrieval_base_delay_s * (2**attempt))
    raise RetrievalError(str(last)) from last
