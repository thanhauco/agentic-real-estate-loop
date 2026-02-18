"""Capstone demo — a simulated 'broker day' across multiple turns and clients.

Ties Phase 1 (answering requests) and Phase 2 (the loops) together and reports
the spec's EVALUATION metrics trending over time:

  * Accuracy        -> hallucination rate, evaluation accuracy
  * Business value   -> lead conversion rate
  * User satisfaction-> evaluation 'overall' score per turn
  * System quality   -> latency, token cost, tool-usage

    python examples/run_broker_session.py
"""
from __future__ import annotations

from _common import rule

from real_estate_loop import RealEstateOrchestrator
from real_estate_loop.loops.evaluation import Feedback

# A scripted day: (label, request, client_id, client_name, feedback)
TURNS = [
    (
        "New lead Emma — investment search",
        "Find me a $700k house near Seattle with good investment potential",
        "client-emma",
        "Emma",
        Feedback(clicked=True, comment="a couple feel too expensive", clicked_listings=["MLS-1013"], price_accurate=True),
    ),
    (
        "Emma returns (no location given — memory should fill it in)",
        "Show me more good investment homes",
        "client-emma",
        "Emma",
        Feedback(clicked=True, clicked_listings=["MLS-1001"], ignored_listings=["MLS-1014"]),
    ),
    (
        "New lead Noah — narrow condo search (weak retrieval)",
        "Find a $520k condo in Queen Anne",
        "client-noah",
        "Noah",
        Feedback(comment="not many options"),
    ),
    (
        "Emma — shortlist + email, she makes an offer",
        "Find Emma's best homes near Seattle under $750k and email her the top picks",
        "client-emma",
        "Emma",
        Feedback(clicked=True, bought=True, clicked_listings=["MLS-1001"]),
    ),
]


def main() -> None:
    orch = RealEstateOrchestrator()
    rule("CAPSTONE — A SIMULATED BROKER DAY (Phase 1 + Phase 2 together)")

    trend: list[tuple[str, float, bool]] = []
    for i, (label, request, client_id, name, feedback) in enumerate(TURNS, 1):
        rule(f"TURN {i} — {label}", "-")
        print(f'request : "{request}"')
        resp = orch.handle(request, client_id=client_id, client_name=name)
        report = orch.improve(feedback)

        ev = report.evaluation
        n_recs = len(resp.recommended_properties)
        print(f"agents  : {resp.agents_used}")
        print(f"result  : {n_recs} recommendation(s); top = "
              f"{resp.recommended_properties[0].property if n_recs else '—'}")
        print(f"eval    : overall {ev.overall:.2f} (relevance {ev.relevance:.2f}, "
              f"completeness {ev.completeness:.2f}, accuracy {ev.accuracy:.2f})")
        if report.total_changes:
            print(f"learned : {report.total_changes} adaptation(s) -> "
                  f"{', '.join(report.all_changes()[:2])}"
                  + (" ..." if report.total_changes > 2 else ""))
        trend.append((f"T{i}", ev.overall, bool(feedback.bought)))
        print()

    # ---- EVALUATION dashboard ------------------------------------------- #
    rule("EVALUATION — satisfaction (overall eval) per turn")
    for tag, overall, bought in trend:
        bar = "#" * int(round(overall * 30))
        flag = "  <- CONVERTED" if bought else ""
        print(f"  {tag}  {overall:0.2f}  {bar}{flag}")

    rule("BUSINESS VALUE + SYSTEM QUALITY (KPIs)")
    for key, value in orch.metrics.summary().items():
        print(f"  {key:22}: {value}")

    rule("WHAT THE SYSTEM LEARNED TODAY")
    print(f"  total adaptations logged : {len(orch.config.changelog)}")
    print(f"  routing(investment)      : {orch.config.routing_table['investment']}")
    print(f"  ranking weights          : {orch.config.ranking_weights}")
    print(f"  retrieval config         : {orch.config.retrieval_config}")
    emma = orch.memory.get_client("client-emma")
    print(f"  Emma profile             : locations={emma.preferred_locations}, "
          f"types={emma.preferred_property_types}, dislikes={emma.dislikes}, "
          f"confidence={emma.confidence}")
    if orch.config.prompt_versions:
        for agent, info in orch.config.prompt_versions.items():
            print(f"  prompt {agent} -> v{info['version']}")


if __name__ == "__main__":
    main()
