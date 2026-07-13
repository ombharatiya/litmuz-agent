"""LLM client contract shared by the decompose, categorize, and judge stages.

Those stages depend only on the LlmClient Protocol, so unit tests inject a deterministic
fake and never call a model. AnthropicClient is the real implementation (lazy import,
integration-tested), mirroring the cite layer's NcbiCrossrefClient pattern: the module
imports with no model SDK installed, and the SDK is only touched at call time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import Config


@dataclass(frozen=True)
class LlmResponse:
    text: str
    model: str


class LlmError(Exception):
    """Any non-recoverable model call failure."""


class LlmTimeout(LlmError):
    """The model call exceeded its deadline."""


class LlmClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> LlmResponse: ...


@dataclass
class AnthropicClient:
    """Real client. Lazily imports the SDK so importing this module needs no dependency."""

    config: Config
    client: object = None

    def __post_init__(self) -> None:
        if self.client is None:
            import anthropic

            self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> LlmResponse:
        # `temperature` is part of the client contract (the deterministic stages ask for 0), but
        # the current Claude models reject the parameter as deprecated, so it is not forwarded to
        # the SDK. Idempotency comes from the cache path (AC-DECOMP-4), not from temperature.
        # `model` lets a non-verdict caller (session titling) select a cheaper model; the
        # verdict stages omit it and get the judge model.
        chosen = model or self.config.judge_model
        try:
            message = self.client.messages.create(  # type: ignore[attr-defined]
                model=chosen,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001  (SDK raises many concrete types)
            raise LlmError(str(exc)) from exc
        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        return LlmResponse(text=text, model=chosen)
