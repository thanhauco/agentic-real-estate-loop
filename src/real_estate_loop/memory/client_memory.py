"""Client (long-term CRM) memory.

A ``ClientProfile`` is not a chat log — it is a *learned* model of the client
that the Memory Evolution Loop (Loop 4) refines from observed behavior, with a
confidence score that grows as evidence accumulates.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class BehaviorSignal(BaseModel):
    """A single observed behavior, e.g. a click or an ignore."""

    kind: str  # "click" | "ignore" | "save" | "reject"
    listing_id: str = ""
    price: float = 0.0
    property_type: str = ""
    neighborhood: str = ""
    note: str = ""


class ClientProfile(BaseModel):
    client_id: str
    budget: float = 0.0
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_property_types: list[str] = Field(default_factory=list)
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    viewed_properties: list[str] = Field(default_factory=list)
    behavior_signals: list[BehaviorSignal] = Field(default_factory=list)
    confidence: float = 0.0  # 0-1, how well we believe we know this client

    def record_view(self, listing_id: str) -> None:
        if listing_id and listing_id not in self.viewed_properties:
            self.viewed_properties.append(listing_id)

    def add_signal(self, signal: BehaviorSignal) -> None:
        self.behavior_signals.append(signal)
        if signal.kind in {"click", "save"} and signal.listing_id:
            self.record_view(signal.listing_id)

    def to_buyer_preferences(self) -> list[str]:
        """Project the learned profile into search preference hints."""
        prefs = list(self.likes)
        for loc in self.preferred_locations:
            prefs.append(f"prefers {loc}")
        for dis in self.dislikes:
            prefs.append(f"avoid {dis}")
        return prefs
