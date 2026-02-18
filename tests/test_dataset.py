"""Tests for the expanded sample dataset."""
from __future__ import annotations

from real_estate_loop.knowledge.data_sources import DataSources

NEW_NEIGHBORHOODS = ["West Seattle", "Mercer Island", "Issaquah", "Shoreline", "Tacoma", "Everett"]


def test_dataset_expanded():
    d = DataSources()
    assert len(d.listings) >= 30
    markets = d.list_markets()
    for n in NEW_NEIGHBORHOODS:
        assert n in markets, f"missing market data for {n}"


def test_listing_ids_unique_and_present():
    d = DataSources()
    ids = [l["id"] for l in d.listings]
    assert len(ids) == len(set(ids)), "duplicate listing ids"
    assert {"MLS-1017", "MLS-1023", "MLS-1030"} <= d.all_listing_ids()


def test_new_comparables_exist():
    d = DataSources()
    assert d.get_comparables("Tacoma", "single_family")
    assert d.get_comparables("Bellevue", "condo")
    assert d.get_comparables("Mercer Island", "condo")
    assert d.get_comparables("Redmond", "townhouse")


def test_affordable_search_surfaces_cheaper_homes():
    d = DataSources()
    res = d.search_listings(location="Tacoma", max_price=500000, property_type="single_family")
    assert any(l["id"] == "MLS-1023" for l in res)


def test_every_listing_neighborhood_has_market_data():
    d = DataSources()
    markets = d.list_markets()
    for listing in d.listings:
        assert listing["neighborhood"] in markets
