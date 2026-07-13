"""Claim categorization (FR / AC-CATEGORY). Fail-closed to safety_critical."""

from .categorizer import categorize, validate_taxonomy_config

__all__ = [
    "categorize",
    "validate_taxonomy_config",
]
