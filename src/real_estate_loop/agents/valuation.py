"""Property Valuation Agent: estimate value from comparable sales."""
from __future__ import annotations

import statistics

from ..core.schemas import Valuation
from .base import AgentResult, BaseAgent


class ValuationAgent(BaseAgent):
    name = "ValuationAgent"

    def _execute(self, task: str, payload: dict) -> AgentResult:
        listing_id = payload.get("property_id") or payload.get("property")
        listing = self.ctx.data.get_listing(listing_id) if listing_id else None
        if not listing:
            return AgentResult(
                result=Valuation(
                    property=listing_id or "",
                    estimated_value="unknown",
                    confidence="low",
                    comparables=[],
                    negotiation_strategy="Cannot value an unknown listing; verify the MLS id.",
                ),
                confidence=0.2,
                next_action="verify_listing_id",
                tools_used=["mls_lookup"],
            )

        comps = self.ctx.data.get_comparables(listing["neighborhood"], listing["property_type"])
        if not comps:
            return AgentResult(
                result=Valuation(
                    property=listing_id,
                    estimated_value="insufficient comparable data",
                    confidence="low",
                    comparables=[],
                    negotiation_strategy="No comparable sales available; gather recent comps before advising.",
                ),
                confidence=0.3,
                next_action="gather_more_comps",
                tools_used=["mls_lookup", "comparables_db"],
            )

        ppsf = [c["sold_price"] / c["sqft"] for c in comps if c.get("sqft")]
        median_ppsf = statistics.median(ppsf)
        subject_sqft = listing["sqft"]
        estimate = median_ppsf * subject_sqft

        spread = (statistics.pstdev(ppsf) if len(ppsf) > 1 else median_ppsf * 0.03) * subject_sqft
        low = estimate - spread
        high = estimate + spread

        price = listing["price"]
        if price > high:
            position = "appears OVERPRICED versus comparables"
            target = f"Open near ${low:,.0f}; comps support up to ${high:,.0f}."
        elif price < low:
            position = "appears UNDERPRICED versus comparables"
            target = f"Move quickly; fair value is ${estimate:,.0f}+ and competition is likely."
        else:
            position = "is priced in line with comparables"
            target = f"Reasonable to offer ${max(low, price*0.97):,.0f}-${price:,.0f}."

        # Confidence: more comps + tighter spread => higher confidence.
        rel_spread = spread / estimate if estimate else 1.0
        conf_score = max(0.3, min(0.9, 0.5 + 0.1 * len(comps) - rel_spread))
        confidence_label = "high" if conf_score >= 0.75 else "medium" if conf_score >= 0.5 else "low"

        fallback = (
            f"Based on {len(comps)} comparable sales at a median ${median_ppsf:,.0f}/sqft, "
            f"the estimated value of {listing['address']} ({subject_sqft:,} sqft) is "
            f"${estimate:,.0f} (range ${low:,.0f}-${high:,.0f}). The ${price:,.0f} list price "
            f"{position}. {target}"
        )
        for directive in self.directives():
            fallback += f" Note: {directive}."

        strategy = self.narrate(
            system="You are a real estate Valuation analyst. Do not guarantee outcomes.",
            user="Explain the valuation and a fair negotiation range for the broker.",
            fallback=fallback,
        )

        result = Valuation(
            property=listing_id,
            estimated_value=f"${estimate:,.0f} (range ${low:,.0f}-${high:,.0f})",
            confidence=confidence_label,
            comparables=[f"{c['address']} — ${c['sold_price']:,.0f}" for c in comps],
            negotiation_strategy=strategy,
        )
        return AgentResult(
            result=result,
            confidence=round(conf_score, 3),
            next_action="include_in_recommendation",
            tools_used=["mls_lookup", "comparables_db"],
        )
