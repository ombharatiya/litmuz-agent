"""Canonical vocabulary and configuration knobs (acceptance criteria §0.1).

Single source of truth. Every stage imports its enums and thresholds from here;
no literal status string or numeric threshold is hard-coded elsewhere. Changing a
knob is a config change, never a code change (model-agnosticism, calibration, caps).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from enum import Enum


class ResolutionStatus(str, Enum):
    """Deterministic citation-resolution outcome (no LLM involved)."""

    OK = "ok"
    METADATA_MISMATCH = "metadata_mismatch"
    FABRICATED = "fabricated"  # well-formed id, authoritatively absent
    UNRESOLVED = "unresolved"  # valid-looking id not located (preprint / too-recent)
    UNKNOWN = "unknown"  # transient failure after bounded backoff; truth undetermined


class SourceStatus(str, Enum):
    """Retraction posture of a resolved source (independent of ResolutionStatus)."""

    ACTIVE = "active"
    RETRACTED = "retracted"
    CONCERN = "concern"  # expression of concern


class RetrievalMode(str, Enum):
    CITED_FULLTEXT = "cited_fulltext"
    CITED_ABSTRACT = "cited_abstract"
    RETRIEVED = "retrieved"
    CALLER_SUPPLIED = "caller_supplied"
    NONE = "none"


class JudgeLabel(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    JUDGE_ERROR = "judge_error"


class Diagnostic(str, Enum):
    D1 = "D1"  # grounded
    D2 = "D2"  # grounded with minor gap
    D3 = "D3"  # unverifiable
    D4 = "D4"  # unsupported
    D5 = "D5"  # contradicted / fabricated


class TrafficLight(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class VerificationMode(str, Enum):
    """What a memo's claims are verified against.

    LITERATURE is the default pipeline (deterministic citation checks against the primary
    literature, then evidence retrieval and entailment judging). GENOMIC checks genomic claims
    against a curated Gladstone reference (Human Accelerated Regions + Zoonomia constraint),
    deterministically and without an LLM judge.
    """

    LITERATURE = "literature"
    GENOMIC = "genomic"


class Category(str, Enum):
    CITATION = "citation"
    MECHANISTIC = "mechanistic"
    SAFETY_CRITICAL = "safety_critical"


class MatchResult(str, Enum):
    """Tri-state so a bare-id citation with no attribution is never a mismatch."""

    TRUE = "true"
    FALSE = "false"
    NOT_APPLICABLE = "not_applicable"  # nothing to compare against (AC-CITE-8)


class IdType(str, Enum):
    PMID = "pmid"
    DOI = "doi"
    PMCID = "pmcid"


# Safety-critical sub-types (config-driven taxonomy; AC-CATEGORY-1).
SAFETY_SUBTYPES: tuple[str, ...] = ("target", "dosing", "indication")


@dataclass(frozen=True)
class Config:
    """Tunable knobs. Defaults are the acceptance-criteria pass lines."""

    judge_model: str = "claude-opus-4-8"
    # A small, cheap model used only to name a session from its memo (never for a verdict).
    title_model: str = "claude-haiku-4-5-20251001"
    high_conf: float = 0.85
    borderline: float = 0.70
    categorizer_conf: float = 0.80
    calibration_threshold: float = 0.75  # conservative: routes more to humans
    top_k: int = 5
    max_input_bytes: int = 51_200
    # Weekly verification quota by tier (calendar week, UTC). Enforced only when auth is on.
    free_weekly_limit: int = 2
    pro_weekly_limit: int = 100
    max_passage_tokens: int = 3_000
    title_match_threshold: float = 0.95
    ncbi_api_key: str | None = None
    retrieval_max_retries: int = 4
    retrieval_base_delay_s: float = 0.5
    # A 'running' job whose updated_at is older than this is presumed orphaned by a dead worker
    # (deploy restart, OOM, task eviction) and becomes reclaimable, like a failed job. Set under
    # the SQS visibility timeout (900s) so a dead job's first redelivery can already reclaim it.
    # update_job_progress refreshes updated_at between claims, but a single slow claim can still
    # age past this while its worker is alive; persist_report is idempotent per job so that such
    # an overlap cannot write a duplicate report (AC-JOB-5).
    stale_running_timeout_s: int = 600

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        """Build a Config from environment variables (upper-snake of the field name).

        Present values override defaults; absent values keep the default. This is
        the single place env is read, so a test asserts the pipeline reads the value
        rather than a literal.
        """
        source = os.environ if env is None else env
        kwargs: dict[str, object] = {}
        for field in fields(cls):
            raw = source.get(field.name.upper())
            if raw is None:
                continue
            kwargs[field.name] = _coerce(field.name, raw, getattr(cls, field.name))
        return cls(**kwargs)


def _coerce(name: str, raw: str, default: object) -> object:
    if name == "ncbi_api_key":
        return raw
    if isinstance(default, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int) and not isinstance(default, bool):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw
