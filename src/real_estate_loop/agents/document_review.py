"""Document Review Agent: extract key terms, flag risks, defer to attorneys."""
from __future__ import annotations

import re

from ..core.schemas import DocumentReview
from .base import AgentResult, BaseAgent

# Clause keywords -> human label. Deterministic, explainable extraction.
_TERM_PATTERNS: dict[str, str] = {
    r"purchase price|sale price": "Purchase price",
    r"earnest money|deposit": "Earnest money / deposit",
    r"closing date|settlement date": "Closing / settlement date",
    r"inspection contingency|inspection period": "Inspection contingency",
    r"financing contingency|loan approval": "Financing contingency",
    r"appraisal contingency": "Appraisal contingency",
    r"commission|listing fee": "Commission / fee",
    r"exclusiv": "Exclusivity clause",
    r"as[- ]is": "As-is sale clause",
    r"title": "Title terms",
    r"contingenc": "Contingencies",
}

# Items that should always be routed to a licensed attorney.
_ATTORNEY_FLAGS: dict[str, str] = {
    r"as[- ]is": "As-is clause limits buyer recourse — attorney should review",
    r"waiv": "Waiver language detected — confirm rights being given up with an attorney",
    r"lien|encumbrance": "Lien/encumbrance language — requires legal review",
    r"arbitration": "Mandatory arbitration clause — attorney should review",
    r"non[- ]refundable": "Non-refundable terms — attorney should review",
    r"indemnif": "Indemnification clause — attorney should review",
}

_RISK_FLAGS: dict[str, str] = {
    r"as[- ]is": "Property sold as-is; budget for unknown repairs",
    r"non[- ]refundable": "Some funds may be non-refundable if the deal falls through",
    r"short closing|close.{0,10}(7|10|14) days": "Short closing window increases financing risk",
    r"no inspection|waive.{0,10}inspection": "Inspection waiver removes a key protection",
}


class DocumentReviewAgent(BaseAgent):
    name = "DocumentReviewAgent"

    @staticmethod
    def _scan(text: str, patterns: dict[str, str]) -> list[str]:
        found: list[str] = []
        for pat, label in patterns.items():
            if re.search(pat, text, flags=re.IGNORECASE):
                if label not in found:
                    found.append(label)
        return found

    def _execute(self, task: str, payload: dict) -> AgentResult:
        doc_type = payload.get("document_type", "document")
        text = payload.get("text", "") or ""

        if not text.strip():
            return AgentResult(
                result=DocumentReview(
                    document_type=doc_type,
                    key_terms=[],
                    risks=[],
                    clauses_summary="No document text was provided to review.",
                    attorney_review_required=["Provide the document text for analysis"],
                ),
                confidence=0.2,
                next_action="request_document",
                tools_used=["document_parser"],
            )

        key_terms = self._scan(text, _TERM_PATTERNS)
        risks = self._scan(text, _RISK_FLAGS)
        attorney = self._scan(text, _ATTORNEY_FLAGS)

        # Pull a couple of money/date facts to make the summary concrete.
        money = re.findall(r"\$[\d,]+(?:\.\d{2})?", text)[:4]
        money_note = f" Detected figures: {', '.join(money)}." if money else ""

        fallback = (
            f"This {doc_type} contains {len(key_terms)} key term(s): "
            f"{', '.join(key_terms) if key_terms else 'none clearly identified'}.{money_note} "
            f"{len(risks)} potential risk area(s) flagged. This summary is informational only "
            f"and is NOT legal advice — items below should be confirmed by a licensed attorney."
        )
        summary = self.narrate(
            system=(
                "You are a real estate Document Review assistant. You are NOT a lawyer. "
                "Summarize plainly and always flag items needing attorney review."
            ),
            user="Summarize the document's important clauses for a broker.",
            fallback=fallback,
        )

        result = DocumentReview(
            document_type=doc_type,
            key_terms=key_terms,
            risks=risks or ["No high-severity risks auto-detected (manual review still advised)"],
            clauses_summary=summary,
            attorney_review_required=attorney or ["General attorney review recommended before signing"],
        )
        confidence = min(0.8, 0.4 + 0.1 * len(key_terms))
        return AgentResult(
            result=result,
            confidence=confidence,
            next_action="route_to_attorney_if_flagged",
            tools_used=["document_parser"],
        )
