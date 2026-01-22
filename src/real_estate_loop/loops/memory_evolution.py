"""Loop 4 — Memory Evolution Loop.

Turns raw behavior (clicks/ignores) into a structured, confidence-scored client
profile — moving from "User likes houses" to a real preference model.
"""
from __future__ import annotations

from ..core.config import RuntimeConfig
from ..knowledge.data_sources import DataSources
from ..memory.client_memory import BehaviorSignal
from ..memory.store import MemoryStore
from .evaluation import CycleContext, Evaluation

_FIXER_HINTS = ("fixer", "dated", "needs updating", "renovation", "original 19")


class MemoryEvolution:
    name = "MemoryEvolution"
    PREMIUM_THRESHOLD = 900_000

    def __init__(self, data: DataSources) -> None:
        self.data = data

    def evolve(
        self,
        ctx: CycleContext,
        evaluation: Evaluation,
        memory: MemoryStore,
        config: RuntimeConfig,
    ) -> list[str]:
        changes: list[str] = []
        fb = ctx.feedback
        if not (fb.clicked_listings or fb.ignored_listings):
            return changes

        profile = memory.get_client(ctx.client_id)

        def add_unique(collection: list[str], value: str) -> bool:
            if value and value not in collection:
                collection.append(value)
                return True
            return False

        # -- Learn from clicks (positive signal) --------------------------- #
        for lid in fb.clicked_listings:
            listing = self.data.get_listing(lid)
            if not listing:
                continue
            profile.add_signal(
                BehaviorSignal(
                    kind="click",
                    listing_id=lid,
                    price=listing["price"],
                    property_type=listing["property_type"],
                    neighborhood=listing["neighborhood"],
                )
            )
            if add_unique(profile.preferred_locations, listing["neighborhood"]):
                changes.append(f"learned preferred location: {listing['neighborhood']}")
            if add_unique(profile.preferred_property_types, listing["property_type"]):
                changes.append(f"learned preferred type: {listing['property_type']}")
            if listing["price"] >= self.PREMIUM_THRESHOLD:
                if add_unique(profile.likes, "premium / higher-end homes"):
                    changes.append("learned preference: premium / higher-end homes")

        # -- Learn from ignores (negative signal) -------------------------- #
        for lid in fb.ignored_listings:
            listing = self.data.get_listing(lid)
            if not listing:
                continue
            profile.add_signal(
                BehaviorSignal(
                    kind="ignore",
                    listing_id=lid,
                    price=listing["price"],
                    property_type=listing["property_type"],
                    neighborhood=listing["neighborhood"],
                    note="ignored",
                )
            )
            desc = listing.get("description", "").lower()
            if any(h in desc for h in _FIXER_HINTS):
                if add_unique(profile.dislikes, "fixer-upper"):
                    changes.append("learned dislike: fixer-uppers")
            if listing["property_type"] == "condo":
                if add_unique(profile.dislikes, "condo"):
                    changes.append("learned dislike: condos")

        # -- Update confidence from accumulated, consistent evidence ------- #
        n_signals = len(profile.behavior_signals)
        new_conf = round(min(0.95, 0.2 + 0.12 * n_signals), 3)
        if new_conf != profile.confidence:
            changes.append(f"profile confidence {profile.confidence} -> {new_conf}")
            profile.confidence = new_conf

        memory.save_client(profile)
        if changes:
            config.log_change(self.name, f"client '{ctx.client_id}': " + "; ".join(changes))
        return changes
