"""Guardrails: keep the system from fabricating data or overstepping.

These are deterministic, explainable checks applied to free text and to listing
references. They implement the spec's GUARDRAILS section:

  Never: fabricate listings, invent property data, provide legal advice,
         guarantee investment returns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schemas import UncertainResponse

# Phrases that imply legal advice (the assistant must defer to an attorney).
_LEGAL_ADVICE_PATTERNS = [
    r"\byou should sue\b",
    r"\blegally (?:you|required|obligated)\b",
    r"\bthis is legal advice\b",
    r"\bi (?:guarantee|certify) (?:the )?(?:contract|title|legality)\b",
    r"\bbreach of contract\b.*\byou (?:will|must) win\b",
]

# Phrases that guarantee financial outcomes (never allowed).
_GUARANTEE_PATTERNS = [
    r"\bguarantee[d]?\b.*\b(?:return|profit|appreciation|roi|gains?)\b",
    r"\b(?:will|is sure to) (?:definitely )?(?:appreciate|double|increase in value)\b",
    r"\brisk[- ]free\b",
    r"\bno risk\b",
    r"\bcan'?t lose\b",
]


@dataclass
class GuardrailReport:
    """Result of scanning text for guardrail violations."""

    legal_advice: list[str] = field(default_factory=list)
    guarantees: list[str] = field(default_factory=list)
    fabricated_ids: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.legal_advice or self.guarantees or self.fabricated_ids)

    @property
    def violations(self) -> list[str]:
        out = []
        out += [f"legal-advice: '{m}'" for m in self.legal_advice]
        out += [f"guarantee: '{m}'" for m in self.guarantees]
        out += [f"fabricated-listing: '{m}'" for m in self.fabricated_ids]
        return out


def scan_text(text: str) -> GuardrailReport:
    """Scan a free-text string for legal-advice and guarantee violations."""
    report = GuardrailReport()
    if not text:
        return report
    lowered = text.lower()
    for pat in _LEGAL_ADVICE_PATTERNS:
        m = re.search(pat, lowered)
        if m:
            report.legal_advice.append(m.group(0))
    for pat in _GUARANTEE_PATTERNS:
        m = re.search(pat, lowered)
        if m:
            report.guarantees.append(m.group(0))
    return report


def validate_listing_ids(referenced_ids: list[str], known_ids: set[str]) -> list[str]:
    """Return any referenced listing ids that are NOT in the known dataset.

    This is the anti-fabrication backstop: the system can only ever talk about
    listings that actually exist in the data sources.
    """
    return [rid for rid in referenced_ids if rid not in known_ids]


def uncertain(reason: str, required_information: list[str] | None = None) -> UncertainResponse:
    """Build the standard 'uncertain' response from the spec."""
    return UncertainResponse(
        status="uncertain",
        reason=reason,
        required_information=required_information or [],
    )
