"""Tests for state persistence (config + memory surviving restarts)."""
from __future__ import annotations

from pathlib import Path

from real_estate_loop import RealEstateOrchestrator
from real_estate_loop.cli import BrokerCLI
from real_estate_loop.core.config import DEFAULT_RANKING_WEIGHTS
from real_estate_loop.core.schemas import Intent
from real_estate_loop.loops.evaluation import Feedback

INVEST = "Find me a $700k investment house near Seattle"


def _train(orch: RealEstateOrchestrator) -> None:
    """Drive a cycle that exercises loops 1, 3, and 4."""
    orch.config.routing_table[Intent.INVESTMENT.value] = ["PropertySearchAgent"]
    orch.handle(INVEST, client_id="emma")
    orch.improve(Feedback(comment="too expensive", clicked_listings=["MLS-1008"]))


def test_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    o1 = RealEstateOrchestrator()
    _train(o1)
    o1.save_state(path)
    assert path.exists()

    o2 = RealEstateOrchestrator()
    assert o2.load_state(path) is True

    # Config knobs restored.
    assert o2.config.ranking_weights == o1.config.ranking_weights
    assert (
        o2.config.routing_table[Intent.INVESTMENT.value]
        == o1.config.routing_table[Intent.INVESTMENT.value]
    )
    assert o2.config.changelog == o1.config.changelog

    # Memory restored.
    emma1 = o1.memory.get_client("emma")
    emma2 = o2.memory.get_client("emma")
    assert emma2.preferred_locations == emma1.preferred_locations
    assert emma2.confidence == emma1.confidence
    assert len(emma2.behavior_signals) == len(emma1.behavior_signals)


def test_restored_state_changes_behavior(tmp_path):
    path = tmp_path / "state.json"
    o1 = RealEstateOrchestrator()
    _train(o1)  # Loop 1 expanded the investment route
    o1.save_state(path)

    o2 = RealEstateOrchestrator()
    o2.load_state(path)
    resp = o2.handle(INVEST, client_id="emma")
    # A fresh orchestrator with restored routing now produces the full answer.
    assert resp.market_analysis is not None
    assert any(p.estimated_value for p in resp.recommended_properties)


def test_load_missing_returns_false(tmp_path):
    o = RealEstateOrchestrator()
    assert o.load_state(tmp_path / "does-not-exist.json") is False


def test_reset_state_restores_defaults():
    o = RealEstateOrchestrator()
    _train(o)
    assert o.config.changelog  # learned something
    o.reset_state()
    assert o.config.ranking_weights == DEFAULT_RANKING_WEIGHTS
    assert o.config.changelog == []
    assert o.memory.all_clients() == {}
    assert o.config.routing_table[Intent.INVESTMENT.value] == [
        "PropertySearchAgent",
        "MarketIntelligenceAgent",
        "ValuationAgent",
    ]


def test_cli_save_and_reset(tmp_path):
    path = str(tmp_path / "s.json")
    cli = BrokerCLI(state_path=path)
    cli.handle_command(INVEST)
    cli.handle_command(":feedback too expensive")
    out = cli.handle_command(":save")
    assert "Saved learned state" in out
    assert Path(path).exists()
    assert "reset" in cli.handle_command(":reset").lower()


def test_cli_save_disabled_without_state_path():
    cli = BrokerCLI()  # no state_path -> persistence off
    assert "disabled" in cli.handle_command(":save").lower()
