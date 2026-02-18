"""Phase 2 tests: each loop adapts the system, and cycles compound."""
from __future__ import annotations

from real_estate_loop import RealEstateOrchestrator
from real_estate_loop.core.config import DEFAULT_RANKING_WEIGHTS
from real_estate_loop.core.schemas import Intent
from real_estate_loop.loops.evaluation import Feedback

INVEST_QUERY = "Find me a $700k house near Seattle with good investment potential"


def _naive(orch: RealEstateOrchestrator) -> None:
    """Degrade routing so the loops have something to learn."""
    orch.config.routing_table[Intent.INVESTMENT.value] = ["PropertySearchAgent"]
    orch.config.routing_table[Intent.SEARCH.value] = ["PropertySearchAgent"]


def test_loop1_intent_optimization_expands_routing():
    orch = RealEstateOrchestrator()
    _naive(orch)
    orch.handle(INVEST_QUERY, client_id="c1")
    report = orch.improve(Feedback(comment="expected market and valuation analysis"))
    route = orch.config.routing_table[Intent.INVESTMENT.value]
    assert "MarketIntelligenceAgent" in route
    assert "ValuationAgent" in route
    assert report.intent_changes  # the loop recorded what it changed


def test_loop3_performance_reweights_on_price_feedback():
    orch = RealEstateOrchestrator()
    orch.handle(INVEST_QUERY, client_id="c1")
    orch.improve(Feedback(comment="these are too expensive / over budget"))
    weights = orch.config.ranking_weights
    assert weights["requirements"] > DEFAULT_RANKING_WEIGHTS["requirements"]
    assert weights["location"] < DEFAULT_RANKING_WEIGHTS["location"]
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_loop4_memory_evolution_learns_profile():
    orch = RealEstateOrchestrator()
    orch.handle(INVEST_QUERY, client_id="emma")
    orch.improve(
        Feedback(
            clicked_listings=["MLS-1008", "MLS-1004"],  # premium homes
            ignored_listings=["MLS-1014"],  # fixer-upper
        )
    )
    profile = orch.memory.get_client("emma")
    assert "Kirkland" in profile.preferred_locations or "Bellevue" in profile.preferred_locations
    assert "fixer-upper" in profile.dislikes
    assert profile.confidence > 0.0
    assert profile.behavior_signals


def test_loop2_retrieval_improves_on_weak_results():
    orch = RealEstateOrchestrator()
    before_version = orch.config.retrieval_config["version"]
    orch.handle("Find a $520k condo in Queen Anne", client_id="noah")
    report = orch.improve(Feedback(comment="not many options"))
    assert report.retrieval_changes
    assert orch.config.retrieval_config["version"] > before_version
    assert orch.config.retrieval_config["rerank"] is True


def test_loop5_prompt_optimizer_versions_prompt():
    orch = RealEstateOrchestrator()
    orch.handle("Find a $520k condo in Queen Anne", client_id="noah")
    orch.improve(Feedback(comment="weak options"))
    entry = orch.config.prompt_versions.get("PropertySearchAgent")
    assert entry is not None
    assert entry["version"] >= 2
    assert entry["directives"]


def test_cycles_compound_to_complete_answer():
    orch = RealEstateOrchestrator()
    _naive(orch)
    resp1 = orch.handle(INVEST_QUERY, client_id="c1")
    assert resp1.market_analysis is None  # naive system: incomplete

    orch.improve(Feedback(comment="expected market and valuation analysis"))

    resp2 = orch.handle(INVEST_QUERY, client_id="c1")
    assert resp2.market_analysis is not None  # learned to be complete
    assert any(p.estimated_value for p in resp2.recommended_properties)


def test_metrics_track_responses_and_quality():
    orch = RealEstateOrchestrator()
    orch.handle(INVEST_QUERY, client_id="c1")
    orch.improve(Feedback(clicked=True, bought=True))
    summary = orch.metrics.summary()
    assert summary["responses"] == 1
    assert summary["conversion_rate"] == 1.0
    assert summary["per_agent_quality"]  # quality back-filled by the eval loop
