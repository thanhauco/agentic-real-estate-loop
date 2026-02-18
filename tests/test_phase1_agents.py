"""Phase 1 unit tests: data, supervisor, agents, guardrails."""
from __future__ import annotations

from real_estate_loop.agents.base import AgentContext
from real_estate_loop.agents.property_search import PropertySearchAgent
from real_estate_loop.agents.supervisor import SupervisorAgent
from real_estate_loop.agents.valuation import ValuationAgent
from real_estate_loop.core.config import RuntimeConfig
from real_estate_loop.core.guardrails import scan_text, validate_listing_ids
from real_estate_loop.core.llm import LLMClient
from real_estate_loop.core.schemas import BuyerProfile, Intent
from real_estate_loop.knowledge.data_sources import DataSources
from real_estate_loop.knowledge.vector_store import SemanticIndex
from real_estate_loop.memory.store import MemoryStore
from real_estate_loop.telemetry.metrics import MetricsCollector


def _ctx() -> AgentContext:
    data = DataSources()
    config = RuntimeConfig()
    return AgentContext(
        llm=LLMClient(),
        data=data,
        memory=MemoryStore(),
        metrics=MetricsCollector(),
        config=config,
        semantic=SemanticIndex(data.listings, config.retrieval_config["metadata_fields"]),
    )


def test_data_sources_load():
    data = DataSources()
    assert len(data.listings) >= 10
    assert "MLS-1013" in data.all_listing_ids()
    assert data.get_market("Ballard") is not None
    assert data.get_comparables("Ballard", "single_family")


def test_supervisor_parsing():
    data = DataSources()
    sup = SupervisorAgent(data, RuntimeConfig())
    plan = sup.plan("Find me a $700k house near Seattle with good investment potential")
    assert plan.buyer_profile.budget == 700_000
    assert plan.buyer_profile.location == "Seattle"
    assert plan.buyer_profile.property_type == "single_family"
    assert Intent.SEARCH in plan.intents
    assert Intent.INVESTMENT in plan.intents
    # Default routing for investment includes the financial agents.
    assert "MarketIntelligenceAgent" in plan.agents
    assert "ValuationAgent" in plan.agents


def test_property_search_ranks_and_filters():
    ctx = _ctx()
    agent = PropertySearchAgent(ctx)
    buyer = BuyerProfile(budget=700_000, location="Seattle", property_type="single_family", bedrooms=3)
    msg = agent.run("find", buyer)
    matches = msg.result
    assert matches, "expected at least one match"
    # Sorted descending by score.
    scores = [m.match_score for m in matches]
    assert scores == sorted(scores, reverse=True)
    # Every returned listing id is real.
    known = ctx.data.all_listing_ids()
    assert all(m.property in known for m in matches)


def test_valuation_produces_estimate():
    ctx = _ctx()
    agent = ValuationAgent(ctx)
    msg = agent.run("value", {"property_id": "MLS-1013"})
    val = msg.result
    assert val.estimated_value.startswith("$")
    assert val.comparables
    assert val.confidence in {"low", "medium", "high"}


def test_guardrails_detect_violations():
    assert scan_text("This is a risk-free investment that will double in value").guarantees
    assert scan_text("Legally you are obligated to sign").legal_advice
    assert scan_text("A solid family home near good schools").ok


def test_validate_listing_ids():
    known = {"MLS-1001", "MLS-1002"}
    assert validate_listing_ids(["MLS-1001"], known) == []
    assert validate_listing_ids(["MLS-9999"], known) == ["MLS-9999"]
