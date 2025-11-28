"""Mutable runtime configuration shared across the system.

Agents *read* from this config; the Loop Engine *writes* to it. This is the
key mechanism that lets the system improve its own behavior over time
(routing, ranking weights, retrieval params, prompt versions).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .schemas import Intent

# Property Search ranking weights (must sum to ~1.0). Tuned by Loop 3.
DEFAULT_RANKING_WEIGHTS: dict[str, float] = {
    "requirements": 0.40,  # buyer requirements (budget, beds, type)
    "location": 0.30,  # location suitability + commute
    "investment": 0.20,  # investment value (appreciation, yield, schools)
    "timing": 0.10,  # market timing (days on market, inventory)
}

# Intent -> ordered list of agent names. Tuned by Loop 1 (Intent Optimization).
# Note: INVESTMENT starts intentionally rich here; the Phase 2 demo shows the
# loop *rediscovering* this expansion after starting from a naive route.
DEFAULT_ROUTING_TABLE: dict[str, list[str]] = {
    Intent.SEARCH.value: ["PropertySearchAgent"],
    Intent.MARKET.value: ["MarketIntelligenceAgent"],
    Intent.VALUATION.value: ["ValuationAgent"],
    Intent.COMMUNICATION.value: ["ClientCommunicationAgent"],
    Intent.DOCUMENT.value: ["DocumentReviewAgent"],
    Intent.INVESTMENT.value: [
        "PropertySearchAgent",
        "MarketIntelligenceAgent",
        "ValuationAgent",
    ],
}

# Retrieval parameters for the semantic knowledge layer. Tuned by Loop 2.
DEFAULT_RETRIEVAL_CONFIG: dict[str, object] = {
    "top_k": 5,
    "rerank": False,
    "metadata_fields": ["neighborhood", "property_type"],
    "version": 1,
}


@dataclass
class RuntimeConfig:
    """All knobs the loops can turn, plus a changelog of adaptations."""

    ranking_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_RANKING_WEIGHTS)
    )
    routing_table: dict[str, list[str]] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_ROUTING_TABLE)
    )
    retrieval_config: dict[str, object] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_RETRIEVAL_CONFIG)
    )
    # Prompt registry: agent_name -> {"version": int, "directives": [str, ...]}
    prompt_versions: dict[str, dict] = field(default_factory=dict)
    # Human-readable log of every change a loop made.
    changelog: list[str] = field(default_factory=list)

    def log_change(self, loop: str, message: str) -> None:
        self.changelog.append(f"[{loop}] {message}")

    def agents_for(self, intents: list[Intent]) -> list[str]:
        """Resolve the (deduplicated, order-preserving) agent set for intents."""
        ordered: list[str] = []
        for intent in intents:
            for agent in self.routing_table.get(intent.value, []):
                if agent not in ordered:
                    ordered.append(agent)
        return ordered

    def prompt_directives(self, agent_name: str) -> list[str]:
        return list(self.prompt_versions.get(agent_name, {}).get("directives", []))
