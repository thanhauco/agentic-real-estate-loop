"""Structured schemas for agent inputs, outputs, and messages.

These mirror the JSON contracts defined in the system specification so every
agent communicates through validated, structured messages.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """High-level user intents the Supervisor can detect in a request."""

    SEARCH = "search"
    MARKET = "market"
    VALUATION = "valuation"
    COMMUNICATION = "communication"
    DOCUMENT = "document"
    INVESTMENT = "investment"


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
class BuyerProfile(BaseModel):
    """Buyer requirements used by the Property Search Agent."""

    budget: float = 0.0
    location: str = ""
    property_type: str = ""
    bedrooms: int = 0
    preferences: list[str] = Field(default_factory=list)
    investment_focus: bool = False


# --------------------------------------------------------------------------- #
# Agent outputs (one per specialized agent)
# --------------------------------------------------------------------------- #
class MarketSummary(BaseModel):
    """Output contract for the Market Intelligence Agent."""

    market_summary: str = ""
    price_trend: str = ""
    investment_score: int = 0  # 0-100
    risks: list[str] = Field(default_factory=list)


class PropertyMatch(BaseModel):
    """A single ranked property from the Property Search Agent."""

    property: str = ""  # listing id
    address: str = ""
    price: float = 0.0
    match_score: float = 0.0  # 0-100
    reason: str = ""
    concerns: list[str] = Field(default_factory=list)


class Valuation(BaseModel):
    """Output contract for the Property Valuation Agent."""

    property: str = ""
    estimated_value: str = ""
    confidence: str = ""
    comparables: list[str] = Field(default_factory=list)
    negotiation_strategy: str = ""


class CommunicationOutput(BaseModel):
    """Output contract for the Client Communication Agent."""

    message: str = ""
    recommended_action: str = ""


class DocumentReview(BaseModel):
    """Output contract for the Document Review Agent."""

    document_type: str = ""
    key_terms: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    clauses_summary: str = ""
    attorney_review_required: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Inter-agent message + uncertainty contracts
# --------------------------------------------------------------------------- #
class AgentMessage(BaseModel):
    """Structured message every agent emits (see spec 'Agent Message Format')."""

    agent: str
    task: str
    input: Any = None
    result: Any = None
    confidence: float = 0.0
    next_action: str = ""


class UncertainResponse(BaseModel):
    """Returned by any agent/guardrail when it cannot proceed confidently."""

    status: str = "uncertain"
    reason: str = ""
    required_information: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Final response contract
# --------------------------------------------------------------------------- #
class RecommendedProperty(BaseModel):
    """A property surfaced in the final recommendation, enriched with valuation."""

    property: str
    address: str
    price: float
    match_score: float
    reason: str
    concerns: list[str] = Field(default_factory=list)
    estimated_value: Optional[str] = None
    negotiation_strategy: Optional[str] = None


class FinalResponse(BaseModel):
    """Top-level response contract returned to the broker."""

    executive_summary: str = ""
    recommended_properties: list[RecommendedProperty] = Field(default_factory=list)
    market_analysis: Optional[MarketSummary] = None
    client_action_plan: list[str] = Field(default_factory=list)
    follow_up_tasks: list[str] = Field(default_factory=list)
    # Operational metadata
    agents_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    uncertain: Optional[UncertainResponse] = None
