"""Entailment judge stage: one claim against its retrieved passages (AC-JUDGE-1..7).

Public API: judge_claim and the pinned JUDGE_SYSTEM_PROMPT. Everything else in
judge.judge is internal.
"""

from .judge import JUDGE_SYSTEM_PROMPT, judge_claim

__all__ = ["JUDGE_SYSTEM_PROMPT", "judge_claim"]
