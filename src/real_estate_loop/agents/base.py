"""Base agent: shared dependencies, telemetry wrapping, and LLM accounting."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..core.config import RuntimeConfig
from ..core.llm import LLMClient
from ..core.schemas import AgentMessage
from ..knowledge.data_sources import DataSources
from ..knowledge.vector_store import SemanticIndex
from ..memory.store import MemoryStore
from ..telemetry.metrics import AgentTelemetry, MetricsCollector


@dataclass
class AgentContext:
    """Shared dependencies handed to every agent (the 'knowledge layer' wiring)."""

    llm: LLMClient
    data: DataSources
    memory: MemoryStore
    metrics: MetricsCollector
    config: RuntimeConfig
    semantic: SemanticIndex


@dataclass
class AgentResult:
    """What an agent's ``_execute`` returns before telemetry wrapping."""

    result: Any
    confidence: float
    next_action: str = ""
    tools_used: list[str] = field(default_factory=list)


class BaseAgent:
    name: str = "BaseAgent"

    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx
        self._tokens = 0

    # -- LLM helper with token accounting ---------------------------------- #
    def narrate(self, system: str, user: str, fallback: str) -> str:
        """Produce a narrative via the LLM client, accumulating token cost."""
        res = self.ctx.llm.generate(system=system, user=user, fallback=fallback)
        self._tokens += res.total_tokens
        return res.text

    def directives(self) -> list[str]:
        """Prompt directives injected by the Prompt Optimizer loop (Loop 5)."""
        return self.ctx.config.prompt_directives(self.name)

    # -- telemetry-wrapped invocation -------------------------------------- #
    def run(self, task: str, payload: Any) -> AgentMessage:
        self._tokens = 0
        start = time.perf_counter()
        success = True
        failure_reason = ""
        try:
            outcome = self._execute(task, payload)
            result = outcome.result
            confidence = outcome.confidence
            next_action = outcome.next_action
            tools_used = outcome.tools_used
        except Exception as exc:  # surface failure as telemetry, not a crash
            result = None
            confidence = 0.0
            next_action = "escalate_to_supervisor"
            tools_used = []
            success = False
            failure_reason = f"{type(exc).__name__}: {exc}"

        latency_ms = (time.perf_counter() - start) * 1000.0
        self.ctx.metrics.record(
            AgentTelemetry(
                agent=self.name,
                task=task,
                latency_ms=round(latency_ms, 3),
                token_cost=self._tokens,
                success=success,
                result_quality=round(confidence, 3),
                tools_used=tools_used,
                failure_reason=failure_reason,
            )
        )
        return AgentMessage(
            agent=self.name,
            task=task,
            input=payload,
            result=result,
            confidence=round(confidence, 3),
            next_action=next_action,
        )

    def _execute(self, task: str, payload: Any) -> AgentResult:  # pragma: no cover
        raise NotImplementedError
