"""Loop 3 — Agent Performance Loop.

Reads telemetry + evaluation signals and retunes the Property Search ranking
weights. Example from the spec: after 'too expensive' feedback, shift weight
toward buyer requirements (budget) and away from raw location preference.
"""
from __future__ import annotations

from ..core.config import RuntimeConfig
from ..telemetry.metrics import MetricsCollector
from .evaluation import CycleContext, Evaluation


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values()) or 1.0
    return {k: round(v / total, 4) for k, v in weights.items()}


class PerformanceOptimizer:
    name = "PerformanceOptimizer"
    STEP = 0.08
    FLOOR = 0.05

    def optimize(
        self,
        ctx: CycleContext,
        evaluation: Evaluation,
        config: RuntimeConfig,
        metrics: MetricsCollector,
    ) -> list[str]:
        changes: list[str] = []
        signals = set(evaluation.signals)
        w = dict(config.ranking_weights)
        before = dict(w)

        if "ranking_mismatch_price" in signals:
            # Buyer is price-sensitive: value requirements (budget) more, location less.
            w["requirements"] += self.STEP
            w["location"] = max(self.FLOOR, w["location"] - self.STEP)
        if "ranking_mismatch_cheap" in signals:
            # Buyer will stretch budget for the right place: value location/investment.
            w["location"] += self.STEP / 2
            w["investment"] += self.STEP / 2
            w["requirements"] = max(self.FLOOR, w["requirements"] - self.STEP)

        # If the search agent is underperforming on quality, lean into investment value.
        quality = metrics.per_agent_quality().get("PropertySearchAgent", 1.0)
        if quality < 0.6 and "ranking_mismatch_cheap" not in signals:
            w["investment"] += self.STEP / 2
            w["timing"] = max(self.FLOOR, w["timing"] - self.STEP / 2)

        w = _normalize(w)
        if w != _normalize(before):
            config.ranking_weights = w
            diff = ", ".join(
                f"{k}: {before[k]:.2f}->{w[k]:.2f}" for k in w if before[k] != w[k]
            )
            msg = f"retuned ranking weights ({diff})"
            config.log_change(self.name, msg)
            changes.append(msg)

        return changes
