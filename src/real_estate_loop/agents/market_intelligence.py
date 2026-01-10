"""Market Intelligence Agent: analyzes neighborhood markets and investment fit."""
from __future__ import annotations

from ..core.schemas import MarketSummary
from .base import AgentResult, BaseAgent


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


class MarketIntelligenceAgent(BaseAgent):
    name = "MarketIntelligenceAgent"

    def _score_market(self, market: dict) -> float:
        """Investment score 0-100 from appreciation, yield, and demand."""
        appreciation = market.get("yoy_appreciation", 0.0)  # %
        yield_pct = market.get("gross_rent_yield", 0.0)  # %
        inventory = market.get("months_inventory", 3.0)

        appreciation_pts = _clamp(appreciation / 10.0 * 50.0, 0, 50)  # up to 50
        yield_pts = _clamp((yield_pct - 3.0) / 2.0 * 20.0, 0, 20)  # 3-5% -> 0-20
        demand_pts = _clamp((3.0 - inventory) / 1.8 * 30.0, 0, 30)  # low inv -> high
        return round(_clamp(appreciation_pts + yield_pts + demand_pts), 1)

    def _risks(self, neighborhood: str, market: dict) -> list[str]:
        risks: list[str] = []
        if market.get("months_inventory", 0) >= 2.0:
            risks.append(f"{neighborhood}: elevated inventory may slow appreciation")
        if market.get("gross_rent_yield", 0) < 3.6:
            risks.append(f"{neighborhood}: rental yield below a typical 3.6% target")
        if market.get("yoy_appreciation", 0) < 5.0:
            risks.append(f"{neighborhood}: below-average year-over-year appreciation")
        if market.get("median_price", 0) > 1_000_000:
            risks.append(f"{neighborhood}: high entry price increases capital exposure")
        return risks

    def _execute(self, task: str, payload: dict) -> AgentResult:
        neighborhoods = payload.get("neighborhoods") or []
        if not neighborhoods:
            # default to the neighborhoods present in the dataset
            neighborhoods = list(self.ctx.data.list_markets().keys())

        scored: list[tuple[str, dict, float]] = []
        for n in neighborhoods:
            market = self.ctx.data.get_market(n)
            if market:
                scored.append((n, market, self._score_market(market)))

        if not scored:
            return AgentResult(
                result=MarketSummary(
                    market_summary="No market data available for the requested area.",
                    price_trend="unknown",
                    investment_score=0,
                    risks=["No matching neighborhood in the market database"],
                ),
                confidence=0.2,
                next_action="request_clarification",
                tools_used=["market_database"],
            )

        scored.sort(key=lambda x: x[2], reverse=True)
        avg_score = round(sum(s for _, _, s in scored) / len(scored))
        best_n, best_m, best_s = scored[0]
        risks: list[str] = []
        for n, m, _ in scored:
            risks.extend(self._risks(n, m))

        trend_bits = [f"{n} {m['price_trend']} ({m['yoy_appreciation']:.1f}% YoY)" for n, m, _ in scored]
        fallback = (
            f"Across {len(scored)} analyzed neighborhood(s), {best_n} leads with an "
            f"investment score of {best_s:.0f}/100 (median ${best_m['median_price']:,.0f}, "
            f"{best_m['yoy_appreciation']:.1f}% YoY appreciation, {best_m['gross_rent_yield']:.1f}% "
            f"gross yield, {best_m['months_inventory']:.1f} months of inventory). "
            f"Overall conditions: {', '.join(trend_bits)}."
        )
        for directive in self.directives():
            fallback += f" Note: {directive}."

        summary_text = self.narrate(
            system="You are a real estate Market Intelligence analyst.",
            user="Summarize these neighborhood market conditions for a broker.",
            fallback=fallback,
        )

        result = MarketSummary(
            market_summary=summary_text,
            price_trend=best_m["price_trend"],
            investment_score=int(avg_score),
            risks=risks or ["No material risks detected in the sample data"],
        )
        confidence = 0.6 + 0.05 * min(len(scored), 4)  # more data -> more confident
        return AgentResult(
            result=result,
            confidence=min(confidence, 0.9),
            next_action="feed_to_valuation",
            tools_used=["market_database"],
        )
