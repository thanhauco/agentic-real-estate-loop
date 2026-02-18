"""Shared pretty-printing helpers for the example scripts."""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``src`` importable when running these scripts directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from real_estate_loop.core.schemas import FinalResponse  # noqa: E402


def rule(title: str = "", char: str = "=") -> None:
    width = 78
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"{char * pad} {title} {char * pad}")
    else:
        print(char * width)


def print_response(resp: FinalResponse) -> None:
    rule("EXECUTIVE SUMMARY", "-")
    print(resp.executive_summary)

    if resp.uncertain:
        rule("UNCERTAIN", "-")
        print(f"status : {resp.uncertain.status}")
        print(f"reason : {resp.uncertain.reason}")
        print(f"need   : {', '.join(resp.uncertain.required_information)}")

    if resp.recommended_properties:
        rule("RECOMMENDED PROPERTIES", "-")
        for i, p in enumerate(resp.recommended_properties, 1):
            print(f"{i}. {p.address}  [{p.property}]")
            print(f"   price        : ${p.price:,.0f}")
            print(f"   match score  : {p.match_score:.0f}/100")
            if p.estimated_value:
                print(f"   est. value   : {p.estimated_value}")
            if p.negotiation_strategy:
                print(f"   negotiation  : {p.negotiation_strategy}")
            if p.concerns:
                print(f"   concerns     : {'; '.join(p.concerns)}")
            print()

    if resp.market_analysis:
        rule("MARKET ANALYSIS", "-")
        m = resp.market_analysis
        print(f"investment score : {m.investment_score}/100")
        print(f"price trend      : {m.price_trend}")
        print(f"summary          : {m.market_summary}")
        if m.risks:
            print("risks            :")
            for r in m.risks:
                print(f"   - {r}")

    if resp.client_action_plan:
        rule("CLIENT ACTION PLAN", "-")
        for step in resp.client_action_plan:
            print(f" - {step}")

    if resp.follow_up_tasks:
        rule("FOLLOW-UP TASKS", "-")
        for task in resp.follow_up_tasks:
            print(f" - {task}")

    if resp.warnings:
        rule("VALIDATOR WARNINGS", "-")
        for w in resp.warnings:
            print(f" ! {w}")

    print(f"\nagents used: {', '.join(resp.agents_used) or '(none)'}")
