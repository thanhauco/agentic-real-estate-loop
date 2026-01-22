"""Loop 1 — Intent Optimization Loop.

Learns better agent routing from outcomes. Example from the spec: the system
discovers that *investment* requests need financial analysis, so it expands the
route from ``[Search]`` to ``[Search, Market, Valuation]``.
"""
from __future__ import annotations

from ..core.config import RuntimeConfig
from ..core.schemas import Intent
from .evaluation import CycleContext, Evaluation


class IntentOptimizer:
    name = "IntentOptimizer"

    def optimize(self, ctx: CycleContext, evaluation: Evaluation, config: RuntimeConfig) -> list[str]:
        changes: list[str] = []
        signals = set(evaluation.signals)

        # Which intents are most relevant to a financial-analysis expansion?
        target_intents = [i for i in ctx.intents if i in (Intent.INVESTMENT, Intent.SEARCH)]
        if not target_intents:
            return changes

        def ensure_agent(intent: Intent, agent: str, reason: str) -> None:
            route = config.routing_table.setdefault(intent.value, [])
            if agent not in route:
                route.append(agent)
                msg = f"intent '{intent.value}' now routes to {agent} ({reason})"
                config.log_change(self.name, msg)
                changes.append(msg)

        if "missing_market_analysis" in signals:
            for intent in target_intents:
                ensure_agent(intent, "MarketIntelligenceAgent", "learned: needs market analysis")
        if "missing_valuation" in signals:
            for intent in target_intents:
                ensure_agent(intent, "ValuationAgent", "learned: needs financial analysis")

        return changes
