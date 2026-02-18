"""Phase 1 demo — the multi-agent orchestrator answering a broker request.

    python examples/run_phase1.py
"""
from __future__ import annotations

from _common import print_response, rule

from real_estate_loop import RealEstateOrchestrator


def main() -> None:
    orchestrator = RealEstateOrchestrator()

    request = "Find me a $700k house near Seattle with good investment potential"
    rule("PHASE 1 — MULTI-AGENT ORCHESTRATOR")
    print(f"\nBroker request:\n  \"{request}\"\n")

    plan = orchestrator.supervisor.plan(request)
    rule("SUPERVISOR PLAN", "-")
    print(plan.rationale)
    print()

    response = orchestrator.handle(request, client_id="client-emma", client_name="Emma")
    print_response(response)

    rule("OBSERVABILITY / TELEMETRY")
    for key, value in orchestrator.metrics.summary().items():
        print(f"  {key:22}: {value}")

    print()
    rule("A SECOND, DIFFERENT INTENT (document review)")
    contract = (
        "PURCHASE CONTRACT. Purchase price $699,000. Earnest money deposit $20,000 "
        "non-refundable after the inspection period of 7 days. Property sold AS-IS. "
        "Buyer waives appraisal contingency. Mandatory arbitration applies."
    )
    doc_resp = orchestrator.handle(
        "Please review this purchase contract for my client",
        client_id="client-emma",
        document_text=contract,
        document_type="purchase contract",
    )
    print_response(doc_resp)


if __name__ == "__main__":
    main()
