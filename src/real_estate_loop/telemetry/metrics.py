"""Observability: per-agent telemetry and aggregate system metrics.

Tracks the signals named in the spec's EVALUATION / Observability sections:
latency, token cost, agent success rate, hallucination rate, conversion rate,
and tool-usage efficiency.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentTelemetry:
    """One record per agent invocation."""

    agent: str
    task: str
    latency_ms: float
    token_cost: int
    success: bool
    result_quality: float = 0.0  # 0-1, filled by the Evaluation loop
    tools_used: list[str] = field(default_factory=list)
    user_feedback: str = ""
    failure_reason: str = ""


class MetricsCollector:
    """Collects telemetry and computes aggregate KPIs."""

    # Approx USD per 1K tokens (illustrative, for cost telemetry only).
    COST_PER_1K_TOKENS = 0.0005

    def __init__(self) -> None:
        self.records: list[AgentTelemetry] = []
        self.hallucinations: int = 0
        self.responses: int = 0
        self.conversions: int = 0

    # -- recording ---------------------------------------------------------- #
    def record(self, telemetry: AgentTelemetry) -> None:
        self.records.append(telemetry)

    def record_response(self, hallucinated: bool, converted: bool = False) -> None:
        self.responses += 1
        if hallucinated:
            self.hallucinations += 1
        if converted:
            self.conversions += 1

    def set_quality(self, agent: str, quality: float, feedback: str = "") -> None:
        """Back-fill result quality after the Evaluation loop runs."""
        for rec in reversed(self.records):
            if rec.agent == agent:
                rec.result_quality = quality
                if feedback:
                    rec.user_feedback = feedback
                break

    # -- aggregates --------------------------------------------------------- #
    @property
    def total_tokens(self) -> int:
        return sum(r.token_cost for r in self.records)

    @property
    def total_cost_usd(self) -> float:
        return round(self.total_tokens / 1000 * self.COST_PER_1K_TOKENS, 6)

    @property
    def avg_latency_ms(self) -> float:
        if not self.records:
            return 0.0
        return round(sum(r.latency_ms for r in self.records) / len(self.records), 2)

    @property
    def agent_success_rate(self) -> float:
        if not self.records:
            return 1.0
        return round(sum(1 for r in self.records if r.success) / len(self.records), 3)

    @property
    def hallucination_rate(self) -> float:
        if not self.responses:
            return 0.0
        return round(self.hallucinations / self.responses, 3)

    @property
    def conversion_rate(self) -> float:
        if not self.responses:
            return 0.0
        return round(self.conversions / self.responses, 3)

    def per_agent_quality(self) -> dict[str, float]:
        sums: dict[str, list[float]] = {}
        for r in self.records:
            sums.setdefault(r.agent, []).append(r.result_quality)
        return {a: round(sum(v) / len(v), 3) for a, v in sums.items() if v}

    def summary(self) -> dict:
        return {
            "invocations": len(self.records),
            "responses": self.responses,
            "avg_latency_ms": self.avg_latency_ms,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "agent_success_rate": self.agent_success_rate,
            "hallucination_rate": self.hallucination_rate,
            "conversion_rate": self.conversion_rate,
            "per_agent_quality": self.per_agent_quality(),
        }
