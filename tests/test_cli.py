"""Tests for the interactive CLI command processor."""
from __future__ import annotations

from real_estate_loop.cli import BrokerCLI


def test_request_returns_recommendations():
    cli = BrokerCLI()
    out = cli.handle_command("Find me a $700k house near Seattle with good investment potential")
    assert "Recommended:" in out
    assert "MLS-" in out
    assert "agents:" in out
    assert cli.has_turn is True


def test_feedback_requires_prior_request():
    cli = BrokerCLI()
    out = cli.handle_command(":feedback bought")
    assert "No prior response" in out


def test_feedback_drives_learning():
    cli = BrokerCLI()
    cli.handle_command("Find me a $700k investment house near Seattle")
    out = cli.handle_command(":feedback these are too expensive, but I clicked MLS-1013")
    assert "evaluation:" in out
    # The price complaint should trigger at least one adaptation.
    assert "adapted" in out or "no adaptations" in out


def test_feedback_parsing_flags():
    fb = BrokerCLI._parse_feedback("bought it, clicked MLS-1001 MLS-1004, price-wrong")
    assert fb.bought is True
    assert fb.clicked is True
    assert fb.price_accurate is False
    assert fb.clicked_listings == ["MLS-1001", "MLS-1004"]

    fb2 = BrokerCLI._parse_feedback("ignored MLS-1014 fixer")
    assert fb2.ignored_listings == ["MLS-1014"]


def test_client_switch_and_inspectors():
    cli = BrokerCLI()
    assert "Active client set to 'emma'" in cli.handle_command(":client emma")
    assert cli.client_id == "emma"
    assert "conversion_rate" in cli.handle_command(":kpis")
    assert "ranking weights" in cli.handle_command(":learned")


def test_help_and_quit():
    cli = BrokerCLI()
    assert "commands:" in cli.handle_command(":help")
    assert cli.handle_command(":quit") is None
    assert cli.handle_command("") == ""
    assert "Unknown command" in cli.handle_command(":bogus")


def test_uncertain_request_is_reported():
    cli = BrokerCLI()
    out = cli.handle_command("I want to buy something")
    assert "uncertain" in out.lower()
