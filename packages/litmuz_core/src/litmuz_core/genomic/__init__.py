"""Genomic verification: check claims against the Gladstone HAR / Zoonomia reference."""

from __future__ import annotations

from .checker import GenomicResult, check_genomic_claim

__all__ = ["GenomicResult", "check_genomic_claim"]
