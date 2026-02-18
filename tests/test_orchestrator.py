"""Orchestrator integration tests (Phase 1 end-to-end)."""
from __future__ import annotations

from real_estate_loop import RealEstateOrchestrator


def test_canonical_investment_query():
    orch = RealEstateOrchestrator()
    resp = orch.handle(
        "Find me a $700k house near Seattle with good investment potential",
        client_id="c1",
    )
    # Recommendations exist and reference only real listings.
    assert resp.recommended_properties
    known = orch.data.all_listing_ids()
    assert all(p.property in known for p in resp.recommended_properties)
    # Default routing means market + valuation are present for investment intent.
    assert resp.market_analysis is not None
    assert any(p.estimated_value for p in resp.recommended_properties)
    assert "PropertySearchAgent" in resp.agents_used
    assert resp.client_action_plan and resp.follow_up_tasks


def test_no_hallucination_flag():
    orch = RealEstateOrchestrator()
    orch.handle("Find a $700k investment house near Seattle", client_id="c1")
    # The single response recorded should not be a hallucination.
    assert orch.metrics.responses == 0  # responses are only counted by the loop engine
    # Validate directly: no fabricated ids in the last response.
    resp = orch._last.response
    known = orch.data.all_listing_ids()
    assert all(p.property in known for p in resp.recommended_properties)


def test_uncertain_when_criteria_missing():
    orch = RealEstateOrchestrator()
    resp = orch.handle("I want to buy something", client_id="c1")
    assert resp.uncertain is not None
    assert resp.uncertain.status == "uncertain"
    assert "budget" in resp.uncertain.required_information


def test_document_review_flow():
    orch = RealEstateOrchestrator()
    contract = (
        "Purchase price $699,000. Earnest money $20,000 non-refundable. "
        "Property sold AS-IS. Buyer waives inspection. Mandatory arbitration."
    )
    resp = orch.handle(
        "Review this purchase contract",
        client_id="c1",
        document_text=contract,
        document_type="purchase contract",
    )
    # Attorney-review items should surface in follow-up tasks.
    assert any("attorney" in t.lower() for t in resp.follow_up_tasks)


def test_telemetry_records_invocations():
    orch = RealEstateOrchestrator()
    orch.handle("Find me a $700k house near Seattle with good investment potential", client_id="c1")
    summary = orch.metrics.summary()
    assert summary["invocations"] >= 3  # search + market + valuation(s)
    assert summary["total_tokens"] > 0
