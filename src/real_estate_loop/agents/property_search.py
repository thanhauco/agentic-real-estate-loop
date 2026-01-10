"""Property Search Agent: find, filter, and rank listings for a buyer.

Ranking follows the spec's weighting (defaults), but the weights live in the
shared RuntimeConfig so the Agent Performance Loop (Loop 3) can retune them:

    40% buyer requirements | 30% location | 20% investment | 10% timing
"""
from __future__ import annotations

from ..core.schemas import BuyerProfile, PropertyMatch
from .base import AgentResult, BaseAgent

_FIXER_HINTS = ("fixer", "dated", "needs updating", "original 19", "renovation")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class PropertySearchAgent(BaseAgent):
    name = "PropertySearchAgent"

    # -- sub-scores (each 0..1) -------------------------------------------- #
    def _requirements_score(self, listing: dict, buyer: BuyerProfile) -> float:
        # budget fit: full credit at/under budget, 0 at +15% over
        if buyer.budget > 0:
            over = (listing["price"] - buyer.budget) / buyer.budget
            budget = 1.0 if over <= 0 else _clamp01(1.0 - over / 0.15)
        else:
            budget = 0.6
        beds = 1.0 if buyer.bedrooms == 0 else _clamp01(listing["bedrooms"] / max(buyer.bedrooms, 1))
        if not buyer.property_type or buyer.property_type == "any":
            ptype = 0.8
        else:
            ptype = 1.0 if listing["property_type"] == buyer.property_type else 0.4
        return 0.5 * budget + 0.3 * beds + 0.2 * ptype

    def _location_score(self, listing: dict, buyer: BuyerProfile) -> float:
        loc = (buyer.location or "").lower()
        hay = f"{listing['neighborhood']} {listing['city']}".lower()
        if not loc or loc in {"any", "seattle area"}:
            match = 0.7
        elif loc in hay:
            match = 1.0
        elif "seattle" in loc:  # metro-level request near our coverage
            match = 0.8
        else:
            match = 0.5
        commute = listing.get("commute_minutes_to_seattle", 30)
        commute_score = _clamp01((40 - commute) / 20.0)  # <=20min ->1, >=40 ->0
        return 0.6 * match + 0.4 * commute_score

    def _investment_score(self, listing: dict) -> float:
        market = self.ctx.data.get_market(listing["neighborhood"]) or {}
        appreciation = _clamp01(market.get("yoy_appreciation", 0) / 8.0)
        yield_pct = _clamp01((market.get("gross_rent_yield", 0) - 3.0) / 2.0)
        school = _clamp01(listing.get("school_score", 5) / 10.0)
        return 0.45 * appreciation + 0.3 * yield_pct + 0.25 * school

    def _timing_score(self, listing: dict) -> float:
        dom = listing.get("days_on_market", 30)
        market = self.ctx.data.get_market(listing["neighborhood"]) or {}
        inventory = market.get("months_inventory", 3.0)
        dom_score = _clamp01((45 - dom) / 38.0)  # <=7 ->~1, >=45 ->0
        inv_score = _clamp01((3.0 - inventory) / 1.8)
        return 0.6 * dom_score + 0.4 * inv_score

    # -- concerns / reasons ------------------------------------------------- #
    def _concerns(self, listing: dict, buyer: BuyerProfile, prefs: list[str]) -> list[str]:
        concerns: list[str] = []
        if buyer.budget and listing["price"] > buyer.budget:
            over = (listing["price"] - buyer.budget) / buyer.budget * 100
            concerns.append(f"${listing['price']:,.0f} is {over:.0f}% over the ${buyer.budget:,.0f} budget")
        if listing.get("hoa_monthly", 0) >= 300:
            concerns.append(f"High HOA of ${listing['hoa_monthly']}/mo")
        desc = listing.get("description", "").lower()
        if any(h in desc for h in _FIXER_HINTS):
            concerns.append("Likely requires renovation (value-add / fixer)")
        if listing.get("days_on_market", 0) >= 30:
            concerns.append(f"On market {listing['days_on_market']} days — investigate why")
        if listing.get("school_score", 10) <= 6:
            concerns.append("Below-average school score")
        for pref in prefs:
            p = pref.lower()
            if p.startswith("avoid") and listing["property_type"] in p:
                concerns.append(f"Conflicts with stated preference: '{pref}'")
        return concerns

    def _execute(self, task: str, payload: dict) -> AgentResult:
        buyer = payload if isinstance(payload, BuyerProfile) else BuyerProfile(**payload)
        prefs = list(buyer.preferences)
        weights = self.ctx.config.ranking_weights

        candidates = self.ctx.data.search_listings(
            location=buyer.location or None,
            max_price=buyer.budget or None,
            min_beds=buyer.bedrooms or None,
            property_type=buyer.property_type or None,
        )

        # Optional semantic relevance boost from the knowledge layer (Loop 2 tunes it).
        sem_scores: dict[str, float] = {}
        if prefs:
            top_k = int(self.ctx.config.retrieval_config.get("top_k", 5))
            for lid, score in self.ctx.semantic.search(" ".join(prefs), top_k=top_k):
                sem_scores[lid] = score

        matches: list[PropertyMatch] = []
        for listing in candidates:
            req = self._requirements_score(listing, buyer)
            loc = self._location_score(listing, buyer)
            inv = self._investment_score(listing)
            tim = self._timing_score(listing)
            base = (
                weights["requirements"] * req
                + weights["location"] * loc
                + weights["investment"] * inv
                + weights["timing"] * tim
            )
            sem_boost = 0.05 * sem_scores.get(listing["id"], 0.0)
            score = _clamp01(base + sem_boost) * 100.0

            reason = (
                f"Requirements {req*100:.0f}%, location {loc*100:.0f}%, "
                f"investment {inv*100:.0f}%, timing {tim*100:.0f}% "
                f"(weighted {score:.0f}/100). {listing['neighborhood']} "
                f"{listing['property_type'].replace('_', ' ')}, {listing['bedrooms']}bd, "
                f"${listing['price']:,.0f}."
            )
            matches.append(
                PropertyMatch(
                    property=listing["id"],
                    address=f"{listing['address']}, {listing['city']}",
                    price=float(listing["price"]),
                    match_score=round(score, 1),
                    reason=reason,
                    concerns=self._concerns(listing, buyer, prefs),
                )
            )

        matches.sort(key=lambda m: m.match_score, reverse=True)
        top = matches[:5]

        if not top:
            return AgentResult(
                result=[],
                confidence=0.3,
                next_action="broaden_search_criteria",
                tools_used=["mls_search"],
            )

        # Confidence reflects how strong the best matches are.
        confidence = _clamp01(0.4 + (top[0].match_score / 100.0) * 0.5)
        return AgentResult(
            result=top,
            confidence=confidence,
            next_action="value_top_matches",
            tools_used=["mls_search", "market_database", "semantic_index"],
        )
