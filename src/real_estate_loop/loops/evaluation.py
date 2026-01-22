"""The Evaluation Agent + the data carried through one improvement cycle.

The Evaluation Agent answers the spec's questions — *Was the recommendation
useful? Did the client click? Did the client buy? Was the price accurate?* — and
emits machine-readable ``signals`` that each optimization loop consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..core.schemas import AgentMessage, BuyerProfile, FinalResponse, Intent
from ..memory.store import MemoryStore


# --------------------------------------------------------------------------- #
# Inputs to a cycle
# --------------------------------------------------------------------------- #
@dataclass
class Feedback:
    """Observed real-world outcome signals for one response."""

    clicked: Optional[bool] = None
    bought: bool = False
    price_accurate: Optional[bool] = None
    comment: str = ""
    clicked_listings: list[str] = field(default_factory=list)
    ignored_listings: list[str] = field(default_factory=list)


@dataclass
class CycleContext:
    """Everything one improvement cycle needs to observe a single response."""

    request: str
    intents: list[Intent]
    buyer: BuyerProfile
    agent_messages: list[AgentMessage]
    response: FinalResponse
    hallucinated: bool
    client_id: str
    feedback: Feedback = field(default_factory=Feedback)
    candidate_count: int = 0


# --------------------------------------------------------------------------- #
# Evaluation output
# --------------------------------------------------------------------------- #
@dataclass
class Evaluation:
    relevance: float  # 0-1
    completeness: float  # 0-1
    accuracy: float  # 0-1
    overall: float  # 0-1
    signals: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    agent_quality: dict[str, float] = field(default_factory=dict)


class EvaluationAgent:
    name = "EvaluationAgent"

    def evaluate(self, ctx: CycleContext, memory: MemoryStore) -> Evaluation:
        intents = set(ctx.intents)
        resp = ctx.response
        signals: list[str] = []
        notes: list[str] = []

        has_recs = bool(resp.recommended_properties)
        has_market = resp.market_analysis is not None
        has_valuation = any(p.estimated_value for p in resp.recommended_properties)

        # -- Completeness vs intent ---------------------------------------- #
        completeness = 1.0
        if Intent.SEARCH in intents and not has_recs:
            signals.append("missing_recommendations")
            completeness -= 0.4
        if Intent.INVESTMENT in intents and not has_market:
            signals.append("missing_market_analysis")
            notes.append("Investment query without market analysis is incomplete.")
            completeness -= 0.3
        if (Intent.INVESTMENT in intents or Intent.VALUATION in intents) and not has_valuation:
            signals.append("missing_valuation")
            notes.append("Investment/valuation query without a value estimate is incomplete.")
            completeness -= 0.3
        completeness = max(0.0, completeness)

        # -- Relevance: how strong are the top matches & were filters honored #
        top_score = resp.recommended_properties[0].match_score if has_recs else 0.0
        relevance = top_score / 100.0
        if has_recs and ctx.buyer.budget:
            over_budget = [p for p in resp.recommended_properties if p.price > ctx.buyer.budget * 1.05]
            if len(over_budget) >= max(1, len(resp.recommended_properties) // 2):
                signals.append("ranking_mismatch_price")
                notes.append("Half or more of recommendations exceed budget by >5%.")
                relevance -= 0.1
        if ctx.candidate_count and ctx.candidate_count <= 2:
            signals.append("weak_retrieval")
            notes.append("Very few candidate listings retrieved.")
        relevance = max(0.0, min(1.0, relevance))

        # -- Accuracy: hallucination + price feedback + valuation confidence #
        accuracy = 0.85
        if ctx.hallucinated:
            signals.append("low_match_accuracy")
            notes.append("Hallucinated listing reference detected by validator.")
            accuracy -= 0.5
        if ctx.feedback.price_accurate is False:
            signals.append("low_match_accuracy")
            notes.append("Broker reported the price estimate was inaccurate.")
            accuracy -= 0.3
        accuracy = max(0.0, min(1.0, accuracy))

        # -- Feedback-driven signals --------------------------------------- #
        comment = (ctx.feedback.comment or "").lower()
        if any(w in comment for w in ("too expensive", "over budget", "expensive")):
            if "ranking_mismatch_price" not in signals:
                signals.append("ranking_mismatch_price")
        if any(w in comment for w in ("too cheap", "more budget", "willing to spend more", "low end")):
            signals.append("ranking_mismatch_cheap")

        # Memory: do we have unconverted behavior we haven't learned from yet?
        profile = memory.get_client(ctx.client_id)
        if (ctx.feedback.clicked_listings or ctx.feedback.ignored_listings) and profile.confidence < 0.6:
            signals.append("low_memory_confidence")

        # -- Per-agent quality (for telemetry back-fill) ------------------- #
        agent_quality: dict[str, float] = {}
        for msg in ctx.agent_messages:
            q = float(msg.confidence)
            if ctx.hallucinated and msg.agent == "PropertySearchAgent":
                q *= 0.6
            if "ranking_mismatch_price" in signals and msg.agent == "PropertySearchAgent":
                q *= 0.8
            agent_quality[msg.agent] = round(max(0.0, min(1.0, q)), 3)

        overall = round(0.4 * completeness + 0.35 * relevance + 0.25 * accuracy, 3)
        # De-duplicate signals, preserve order.
        signals = list(dict.fromkeys(signals))
        return Evaluation(
            relevance=round(relevance, 3),
            completeness=round(completeness, 3),
            accuracy=round(accuracy, 3),
            overall=overall,
            signals=signals,
            notes=notes,
            agent_quality=agent_quality,
        )
