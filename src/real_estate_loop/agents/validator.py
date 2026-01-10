"""Response Validator: the quality gate before a response reaches the broker.

Implements the spec's 'Validation Agent' node. It enforces guardrails across all
agent output and verifies that every referenced listing actually exists in the
data sources (the anti-hallucination backstop).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..core.guardrails import GuardrailReport, scan_text, validate_listing_ids
from ..core.schemas import AgentMessage, FinalResponse


@dataclass
class ValidationResult:
    ok: bool
    hallucinated: bool
    warnings: list[str] = field(default_factory=list)
    guardrail: GuardrailReport = field(default_factory=GuardrailReport)


def _collect_text(response: FinalResponse) -> str:
    parts = [response.executive_summary]
    parts += response.client_action_plan
    parts += response.follow_up_tasks
    for p in response.recommended_properties:
        parts += [p.reason, p.negotiation_strategy or ""]
    if response.market_analysis:
        parts.append(response.market_analysis.market_summary)
    return "\n".join(parts)


class ResponseValidator:
    name = "ResponseValidator"

    def __init__(self, known_listing_ids: set[str]) -> None:
        self.known_listing_ids = known_listing_ids

    def validate(self, response: FinalResponse, agent_messages: list[AgentMessage]) -> ValidationResult:
        warnings: list[str] = []

        # 1) Guardrail scan over all generated narrative text.
        text = _collect_text(response)
        report = scan_text(text)

        # 2) Anti-fabrication: every recommended listing id must be known.
        referenced = [p.property for p in response.recommended_properties]
        fabricated = validate_listing_ids(referenced, self.known_listing_ids)
        report.fabricated_ids = fabricated
        hallucinated = bool(fabricated)

        if report.legal_advice:
            warnings.append("Flagged potential legal-advice phrasing (defer to attorney).")
        if report.guarantees:
            warnings.append("Flagged guarantee-style language about returns (not permitted).")
        if fabricated:
            warnings.append(f"Dropped {len(fabricated)} fabricated listing reference(s): {fabricated}.")

        # 3) Completeness sanity checks.
        empty = (
            not response.recommended_properties
            and response.market_analysis is None
            and response.uncertain is None
            and not response.follow_up_tasks
        )
        if empty:
            warnings.append("Response has neither recommendations nor analysis.")

        return ValidationResult(
            ok=report.ok,
            hallucinated=hallucinated,
            warnings=warnings,
            guardrail=report,
        )
