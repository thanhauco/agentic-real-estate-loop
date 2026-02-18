"""Tests for the web JSON API router (no sockets needed)."""
from __future__ import annotations

from pathlib import Path

from real_estate_loop.web import server
from real_estate_loop.web.api import ApiRouter

INVEST = "Find me a $700k investment house near Seattle"


def test_handle_returns_full_response():
    r = ApiRouter()
    res = r.dispatch("POST", "/api/handle", {"request": INVEST})
    assert res.status == 200
    resp = res.payload["response"]
    assert resp["recommended_properties"]
    assert resp["market_analysis"] is not None


def test_handle_missing_request_is_400():
    r = ApiRouter()
    assert r.dispatch("POST", "/api/handle", {}).status == 400


def test_feedback_requires_prior_handle():
    r = ApiRouter()
    assert r.dispatch("POST", "/api/feedback", {"comment": "hi"}).status == 400


def test_feedback_after_handle_learns():
    r = ApiRouter()
    r.dispatch("POST", "/api/handle", {"request": INVEST})
    res = r.dispatch(
        "POST", "/api/feedback", {"comment": "too expensive", "clicked_listings": ["MLS-1008"]}
    )
    assert res.status == 200
    assert "evaluation" in res.payload
    assert "changes" in res.payload


def test_kpis_and_learned_routes():
    r = ApiRouter()
    r.dispatch("POST", "/api/handle", {"request": INVEST})
    r.dispatch("POST", "/api/feedback", {"comment": "too expensive"})
    kpis = r.dispatch("GET", "/api/kpis", {})
    assert kpis.status == 200 and "conversion_rate" in kpis.payload
    learned = r.dispatch("GET", "/api/learned", {})
    assert learned.status == 200
    assert "ranking_weights" in learned.payload
    assert "changelog" in learned.payload


def test_reset_route_clears_learning():
    r = ApiRouter()
    r.dispatch("POST", "/api/handle", {"request": INVEST})
    r.dispatch("POST", "/api/feedback", {"comment": "too expensive"})
    assert r.dispatch("POST", "/api/reset", {}).status == 200
    learned = r.dispatch("GET", "/api/learned", {}).payload
    assert learned["changelog"] == []


def test_unknown_route_is_404():
    assert ApiRouter().dispatch("GET", "/api/nope", {}).status == 404


def test_router_persists_state(tmp_path):
    path = str(tmp_path / "state.json")
    r1 = ApiRouter(state_path=path)
    r1.dispatch("POST", "/api/handle", {"request": INVEST})
    r1.dispatch("POST", "/api/feedback", {"comment": "too expensive"})
    assert Path(path).exists()

    r2 = ApiRouter(state_path=path)
    assert r2.dispatch("GET", "/api/learned", {}).payload["changelog"]


def test_index_html_present_and_wired():
    idx = server._STATIC_DIR / "index.html"
    assert idx.is_file()
    text = idx.read_text(encoding="utf-8")
    assert "/api/handle" in text
    assert "Real Estate AI" in text
