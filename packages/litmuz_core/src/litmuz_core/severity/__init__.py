"""Severity stage: deterministic mapping from verdict to diagnostic and routing."""

from __future__ import annotations

from .mapping import SeverityResult, human_review_light, score_claim

__all__ = ["SeverityResult", "score_claim", "human_review_light"]
