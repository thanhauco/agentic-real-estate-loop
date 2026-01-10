"""Supervisor Agent: understand intent, build the buyer profile, plan routing."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.config import RuntimeConfig
from ..core.schemas import BuyerProfile, Intent
from ..knowledge.data_sources import DataSources


@dataclass
class SupervisorPlan:
    request: str
    intents: list[Intent]
    buyer_profile: BuyerProfile
    agents: list[str]
    rationale: str = ""
    target_neighborhoods: list[str] = field(default_factory=list)


# Intent trigger keywords.
_INTENT_KEYWORDS: dict[Intent, tuple[str, ...]] = {
    Intent.SEARCH: ("find", "search", "looking for", "house", "home", "property", "listing", "buy"),
    Intent.MARKET: ("market", "trend", "neighborhood", "appreciation", "area"),
    Intent.VALUATION: ("value", "worth", "appraise", "overpriced", "negotiate", "price check"),
    Intent.COMMUNICATION: ("email", "follow up", "follow-up", "message", "write to", "reach out"),
    Intent.DOCUMENT: ("contract", "inspection report", "listing agreement", "document", "review the"),
    Intent.INVESTMENT: ("investment", "invest", "roi", "rental", "cash flow", "cap rate", "return"),
}

_TYPE_KEYWORDS: dict[str, str] = {
    "condo": "condo",
    "townhouse": "townhouse",
    "townhome": "townhouse",
    "single family": "single_family",
    "single-family": "single_family",
    "house": "single_family",
    "home": "single_family",
}


class SupervisorAgent:
    name = "SupervisorAgent"

    def __init__(self, data: DataSources, config: RuntimeConfig) -> None:
        self.data = data
        self.config = config
        self._known_neighborhoods = list(data.list_markets().keys())

    # -- request parsing ---------------------------------------------------- #
    def _detect_intents(self, text: str) -> list[Intent]:
        low = text.lower()
        intents: list[Intent] = []
        for intent, kws in _INTENT_KEYWORDS.items():
            if any(kw in low for kw in kws):
                intents.append(intent)
        if not intents:
            intents.append(Intent.SEARCH)  # safe default
        return intents

    @staticmethod
    def _parse_budget(text: str) -> float:
        low = text.lower().replace(",", "")
        # $700k / 700k
        m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*k\b", low)
        if m:
            return float(m.group(1)) * 1_000
        # $1.2m / 1.2 million
        m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:m|million)\b", low)
        if m:
            return float(m.group(1)) * 1_000_000
        # $700000
        m = re.search(r"\$\s*(\d{5,})", low)
        if m:
            return float(m.group(1))
        return 0.0

    @staticmethod
    def _parse_bedrooms(text: str) -> int:
        m = re.search(r"(\d+)\s*(?:\+)?\s*(?:bed|br|bedroom)", text.lower())
        return int(m.group(1)) if m else 0

    def _parse_location(self, text: str) -> str:
        low = text.lower()
        for n in self._known_neighborhoods:
            if n.lower() in low:
                return n
        for city in ("bellevue", "redmond", "kirkland", "renton", "sammamish", "seattle"):
            if city in low:
                return city.title()
        return ""

    @staticmethod
    def _parse_type(text: str) -> str:
        low = text.lower()
        for kw, canonical in _TYPE_KEYWORDS.items():
            if kw in low:
                return canonical
        return ""

    # -- planning ----------------------------------------------------------- #
    def plan(self, request: str) -> SupervisorPlan:
        intents = self._detect_intents(request)
        investment_focus = Intent.INVESTMENT in intents

        buyer = BuyerProfile(
            budget=self._parse_budget(request),
            location=self._parse_location(request),
            property_type=self._parse_type(request),
            bedrooms=self._parse_bedrooms(request),
            investment_focus=investment_focus,
        )

        agents = self.config.agents_for(intents)

        # Target neighborhoods for the Market agent: the requested one (+ peers),
        # otherwise the whole coverage area.
        if buyer.location and buyer.location in self._known_neighborhoods:
            targets = [buyer.location]
        elif buyer.location.lower() == "seattle":
            targets = [n for n in self._known_neighborhoods if n in ("Ballard", "Queen Anne")]
            targets += ["Bellevue", "Redmond", "Kirkland"]
        else:
            targets = list(self._known_neighborhoods)

        rationale = (
            f"Detected intents {[i.value for i in intents]}; routed to {agents}. "
            f"Budget=${buyer.budget:,.0f}, location='{buyer.location or 'any'}', "
            f"type='{buyer.property_type or 'any'}', beds={buyer.bedrooms or 'any'}, "
            f"investment_focus={investment_focus}."
        )
        return SupervisorPlan(
            request=request,
            intents=intents,
            buyer_profile=buyer,
            agents=agents,
            rationale=rationale,
            target_neighborhoods=targets,
        )
