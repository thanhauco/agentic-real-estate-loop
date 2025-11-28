"""LLM client abstraction.

The system is designed to run fully offline: every agent computes its numeric
results deterministically and supplies a ``fallback`` narrative. In MOCK mode
(the default) the client returns that fallback verbatim, so outputs are stable
and testable. If a provider is configured via environment variables, the client
asks the real model to *polish* the fallback narrative instead.

Token usage is always estimated so the telemetry / observability layer can
report "tool usage efficiency" and token cost regardless of mode.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) good enough for cost telemetry."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


class LLMClient:
    """Pluggable LLM client. Auto-detects provider from the environment."""

    def __init__(self, model: str | None = None) -> None:
        self.provider, self.model = self._detect_provider(model)
        self._client = None  # lazily constructed for real providers

    # -- provider detection ------------------------------------------------- #
    @staticmethod
    def _detect_provider(model: str | None) -> tuple[str, str]:
        if os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"):
            return "azure", os.getenv("AZURE_OPENAI_DEPLOYMENT", model or "gpt-4o-mini")
        if os.getenv("OPENAI_API_KEY"):
            return "openai", os.getenv("REL_LLM_MODEL", model or "gpt-4o-mini")
        return "mock", model or "mock-deterministic"

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock"

    # -- main entry point --------------------------------------------------- #
    def generate(self, system: str, user: str, fallback: str, temperature: float = 0.2) -> LLMResult:
        """Return a narrative.

        In mock mode the deterministic ``fallback`` is returned. With a real
        provider, the model is asked to lightly polish ``fallback`` while
        preserving every fact (no fabrication).
        """
        prompt_tokens = _estimate_tokens(system) + _estimate_tokens(user) + _estimate_tokens(fallback)

        if self.provider == "mock":
            return LLMResult(
                text=fallback,
                prompt_tokens=prompt_tokens,
                completion_tokens=_estimate_tokens(fallback),
                model=self.model,
            )

        try:
            text = self._call_real(system, user, fallback, temperature)
        except Exception:  # pragma: no cover - network/credential failures
            # Fail safe: never let a provider error break the pipeline.
            text = fallback

        return LLMResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=_estimate_tokens(text),
            model=self.model,
        )

    # -- real provider plumbing -------------------------------------------- #
    def _call_real(self, system: str, user: str, fallback: str, temperature: float) -> str:
        from openai import AzureOpenAI, OpenAI  # imported lazily

        if self._client is None:
            if self.provider == "azure":
                self._client = AzureOpenAI(
                    api_key=os.environ["AZURE_OPENAI_API_KEY"],
                    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01"),
                )
            else:
                self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        guard = (
            "You are polishing an internal real-estate analysis for a broker. "
            "Rewrite the DRAFT to be clear and professional. Do NOT add, invent, "
            "or change any numbers, addresses, or facts. Do NOT give legal advice "
            "or guarantee returns."
        )
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": f"{system}\n\n{guard}"},
                {"role": "user", "content": f"{user}\n\nDRAFT:\n{fallback}"},
            ],
        )
        return (resp.choices[0].message.content or fallback).strip()
