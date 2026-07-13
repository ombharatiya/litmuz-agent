"""Turn a resolved citation into a deterministic CitationCheck (AC-CITE-1..10).

No LLM anywhere in this module or its dependencies. The severity stage (Phase 2)
consumes ``resolution_status`` and ``source_status``; a fabricated citation is forced
to red and never reaches the judge, and a retracted/EoC source can never auto-pass.
"""

from __future__ import annotations

from ..config import Config, MatchResult, ResolutionStatus
from ..schemas import CitationCheck, CitedId, ClaimAttribution
from . import matching
from .clients import MetadataClient, Resolution, ResolutionOutcome, TransientError

# A cache maps an identifier key -> a Resolution. Transient failures are never cached.
ResolutionCache = dict[str, Resolution]


def identifier_key(cited_id: CitedId) -> str:
    return f"{cited_id.id_type.value}:{cited_id.value}"


def check_citation(
    cited_id: CitedId,
    attribution: ClaimAttribution | None,
    client: MetadataClient,
    config: Config,
    cache: ResolutionCache | None = None,
) -> CitationCheck:
    key = identifier_key(cited_id)
    base = CitationCheck(
        identifier=key, id_type=cited_id.id_type, resolution_status=ResolutionStatus.UNKNOWN
    )

    resolution = cache.get(key) if cache is not None else None
    if resolution is None:
        try:
            resolution = client.resolve(cited_id)
        except TransientError:
            # Truth undetermined; never fabricated, never ok. Not cached.
            return base.model_copy(update={"resolver_path": "transient"})
        if cache is not None:
            cache[key] = resolution

    return _to_check(cited_id, attribution, resolution, config)


def _to_check(
    cited_id: CitedId,
    attribution: ClaimAttribution | None,
    resolution: Resolution,
    config: Config,
) -> CitationCheck:
    key = identifier_key(cited_id)

    if resolution.outcome is ResolutionOutcome.ABSENT:
        return CitationCheck(
            identifier=key,
            id_type=cited_id.id_type,
            resolution_status=ResolutionStatus.FABRICATED,
            resolver_path=resolution.resolver_path,
        )
    if resolution.outcome is ResolutionOutcome.UNRESOLVED:
        return CitationCheck(
            identifier=key,
            id_type=cited_id.id_type,
            resolution_status=ResolutionStatus.UNRESOLVED,
            resolver_path=resolution.resolver_path,
        )

    record = resolution.record
    assert record is not None  # FOUND always carries a record
    attribution = attribution or ClaimAttribution()

    title_m = matching.title_match(attribution.title, record.title, config.title_match_threshold)
    author_m = matching.author_match(attribution.surnames, list(record.surnames))
    year_m = matching.year_match(attribution.year, record.years)

    applicable = [m for m in (title_m, author_m, year_m) if m is not MatchResult.NOT_APPLICABLE]
    status = (
        ResolutionStatus.METADATA_MISMATCH
        if any(m is MatchResult.FALSE for m in applicable)
        else ResolutionStatus.OK
    )

    return CitationCheck(
        identifier=key,
        id_type=cited_id.id_type,
        resolution_status=status,
        source_status=record.source_status,
        title_match=title_m,
        author_match=author_m,
        year_match=year_m,
        resolver_path=resolution.resolver_path,
    )
