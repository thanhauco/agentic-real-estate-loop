"""Broker (long-term) memory: active listings, client pipeline, sales history."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineEntry:
    client_id: str
    stage: str = "new"  # new | nurturing | touring | offer | closed | lost
    note: str = ""


@dataclass
class BrokerMemory:
    active_listings: list[str] = field(default_factory=list)
    client_pipeline: list[PipelineEntry] = field(default_factory=list)
    sales_history: list[dict] = field(default_factory=list)

    def upsert_pipeline(self, client_id: str, stage: str, note: str = "") -> None:
        for entry in self.client_pipeline:
            if entry.client_id == client_id:
                entry.stage = stage
                if note:
                    entry.note = note
                return
        self.client_pipeline.append(PipelineEntry(client_id=client_id, stage=stage, note=note))

    def record_sale(self, listing_id: str, client_id: str, price: float) -> None:
        self.sales_history.append(
            {"listing_id": listing_id, "client_id": client_id, "price": price}
        )
