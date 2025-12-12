"""Data sources: the knowledge layer's connectors to MLS / market / comps.

In this reference implementation the connectors read from the bundled
``data/*.json`` sample files. Swapping these methods for real MLS / Zillow /
Redfin clients is the only change needed to go live — the agents above are
unaware of the data origin.

The set of *known* listing ids returned here is the single source of truth the
anti-fabrication guardrail validates against.
"""
from __future__ import annotations

import json
from pathlib import Path


def _default_data_dir() -> Path:
    # repo_root/data  (this file is src/real_estate_loop/knowledge/data_sources.py)
    return Path(__file__).resolve().parents[3] / "data"


class DataSources:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else _default_data_dir()
        self._listings: list[dict] = []
        self._markets: dict[str, dict] = {}
        self._comparables: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        listings_doc = json.loads((self.data_dir / "listings.json").read_text(encoding="utf-8"))
        self._listings = listings_doc["listings"]
        market_doc = json.loads((self.data_dir / "market_data.json").read_text(encoding="utf-8"))
        self._markets = market_doc["markets"]
        comps_doc = json.loads((self.data_dir / "comparables.json").read_text(encoding="utf-8"))
        self._comparables = comps_doc["comparables"]

    # -- listings ----------------------------------------------------------- #
    @property
    def listings(self) -> list[dict]:
        return self._listings

    def all_listing_ids(self) -> set[str]:
        return {l["id"] for l in self._listings}

    def get_listing(self, listing_id: str) -> dict | None:
        return next((l for l in self._listings if l["id"] == listing_id), None)

    def search_listings(
        self,
        location: str | None = None,
        max_price: float | None = None,
        min_beds: int | None = None,
        property_type: str | None = None,
    ) -> list[dict]:
        """Filter sample listings. Returns only real entries from the dataset."""
        results = []
        loc = (location or "").strip().lower()
        for l in self._listings:
            if l.get("listing_status") != "active":
                continue
            if max_price is not None and l["price"] > max_price * 1.10:
                # allow a 10% stretch band so near-budget options can surface
                continue
            if min_beds and l["bedrooms"] < min_beds:
                continue
            if property_type and property_type != "any" and l["property_type"] != property_type:
                continue
            if loc and loc not in {"any", "seattle area", "puget sound"}:
                hay = f"{l['neighborhood']} {l['city']}".lower()
                # match if the requested location names a city/neighborhood we cover,
                # OR the requested location is a metro ('seattle') near our coverage
                if loc not in hay and "seattle" not in loc:
                    continue
            results.append(l)
        return results

    # -- market ------------------------------------------------------------- #
    def get_market(self, neighborhood: str) -> dict | None:
        return self._markets.get(neighborhood)

    def list_markets(self) -> dict[str, dict]:
        return dict(self._markets)

    # -- comparables -------------------------------------------------------- #
    def get_comparables(self, neighborhood: str, property_type: str) -> list[dict]:
        return list(self._comparables.get(f"{neighborhood}|{property_type}", []))
