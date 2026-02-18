"""Phase 2 demo — Loop Engineering: the system improving its own workflow.

    python examples/run_phase2_loops.py

Walks through all five loops with explicit before/after state so you can see the
system adapt: routing (Loop 1), retrieval (Loop 2), ranking (Loop 3), memory
(Loop 4), and prompts (Loop 5).
"""
from __future__ import annotations

from _common import rule

from real_estate_loop import RealEstateOrchestrator
from real_estate_loop.core.schemas import Intent
from real_estate_loop.loops.evaluation import Feedback


def print_report(report) -> None:
    ev = report.evaluation
    print(
        f"  evaluation -> overall {ev.overall:.2f} "
        f"(relevance {ev.relevance:.2f}, completeness {ev.completeness:.2f}, "
        f"accuracy {ev.accuracy:.2f})"
    )
    if ev.signals:
        print(f"  signals    -> {', '.join(ev.signals)}")
    changes = report.all_changes()
    if changes:
        print("  adaptations:")
        for c in changes:
            print(f"     - {c}")
    else:
        print("  adaptations: (none this cycle)")


def main() -> None:
    orch = RealEstateOrchestrator()
    query = "Find me a $700k house near Seattle with good investment potential"

    rule("PHASE 2 — LOOP ENGINEERING")

    # Start from a deliberately NAIVE route so we can watch Loop 1 learn.
    orch.config.routing_table[Intent.INVESTMENT.value] = ["PropertySearchAgent"]
    print("\nNaive starting routing for 'investment':")
    print(f"  {orch.config.routing_table[Intent.INVESTMENT.value]}")
    weights_before = dict(orch.config.ranking_weights)
    print(f"Starting ranking weights: {weights_before}")

    # ---- Cycle 1: incomplete answer, then learn ---------------------------- #
    rule("CYCLE 1 — investment query on the naive system", "-")
    resp1 = orch.handle(query, client_id="client-emma", client_name="Emma")
    print(f"agents used      : {resp1.agents_used}")
    print(f"has market block : {resp1.market_analysis is not None}")
    print(f"has valuations   : {any(p.estimated_value for p in resp1.recommended_properties)}")

    print("\nBroker feedback: 'Useful, but these look too expensive for the returns, "
          "and I expected market + valuation analysis.'")
    report1 = orch.improve(
        Feedback(
            clicked=True,
            comment="too expensive for the investment returns; expected market and valuation analysis",
            price_accurate=True,
        )
    )
    print()
    print_report(report1)

    # ---- Cycle 2: same query, improved system ------------------------------ #
    rule("CYCLE 2 — same query after the loops adapted", "-")
    print(f"Routing for 'investment' is now: {orch.config.routing_table[Intent.INVESTMENT.value]}")
    print(f"Ranking weights are now        : {orch.config.ranking_weights}")
    resp2 = orch.handle(query, client_id="client-emma", client_name="Emma")
    print(f"\nagents used      : {resp2.agents_used}")
    print(f"has market block : {resp2.market_analysis is not None}")
    print(f"has valuations   : {any(p.estimated_value for p in resp2.recommended_properties)}")
    print("=> Loop 1 expanded routing; Loop 3 reweighted ranking; the answer is now complete.")

    # ---- Loop 4: Memory Evolution ------------------------------------------ #
    rule("LOOP 4 — Memory Evolution", "-")
    print("Client browses: clicks two premium homes, ignores a fixer-upper.")
    orch.improve(
        Feedback(
            clicked_listings=["MLS-1008", "MLS-1004"],  # premium
            ignored_listings=["MLS-1014"],  # fixer-upper
        )
    )
    profile = orch.memory.get_client("client-emma")
    print(f"  preferred_locations : {profile.preferred_locations}")
    print(f"  preferred_types     : {profile.preferred_property_types}")
    print(f"  likes               : {profile.likes}")
    print(f"  dislikes            : {profile.dislikes}")
    print(f"  confidence          : {profile.confidence}")

    # ---- Loop 2: Retrieval Improvement ------------------------------------- #
    rule("LOOP 2 — Retrieval Improvement", "-")
    print(f"Retrieval config before: {orch.config.retrieval_config}")
    # A narrow query that returns very few candidates -> weak retrieval signal.
    orch.handle("Find a $520k condo in Queen Anne", client_id="client-noah", client_name="Noah")
    report_retrieval = orch.improve(Feedback(comment="not many options"))
    print_report(report_retrieval)
    print(f"Retrieval config after : {orch.config.retrieval_config}")

    # ---- Wrap up: full changelog + KPIs ------------------------------------ #
    rule("CONFIG CHANGELOG (everything the loops changed)")
    for entry in orch.config.changelog:
        print(f"  {entry}")

    rule("SYSTEM KPIs")
    for key, value in orch.metrics.summary().items():
        print(f"  {key:22}: {value}")

    rule("PROMPT VERSIONS (Loop 5)")
    for agent, info in orch.config.prompt_versions.items():
        print(f"  {agent}: v{info['version']} directives={info['directives']}")


if __name__ == "__main__":
    main()
