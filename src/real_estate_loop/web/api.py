"""JSON API router for the web front end.

The router is deliberately transport-agnostic and free of socket I/O so it can be
unit-tested directly. ``server.py`` is a thin HTTP layer on top of it.

Routes:
    POST /api/handle    {request, client_id?, client_name?}      -> FinalResponse
    POST /api/feedback  {clicked?, bought?, price_accurate?,
                         comment?, clicked_listings?, ignored_listings?} -> LoopReport
    GET  /api/kpis                                                -> telemetry summary
    GET  /api/learned                                            -> config + memory snapshot
    POST /api/reset                                              -> factory reset
"""
from __future__ import annotations

import dataclasses
import threading
from dataclasses import dataclass

from ..loops.evaluation import Feedback
from ..orchestrator import RealEstateOrchestrator


@dataclass
class ApiResult:
    status: int
    payload: dict


class ApiRouter:
    def __init__(
        self,
        orchestrator: RealEstateOrchestrator | None = None,
        state_path: str | None = None,
    ) -> None:
        self.orch = orchestrator or RealEstateOrchestrator()
        self.state_path = state_path
        self._lock = threading.Lock()
        if state_path:
            self.orch.load_state(state_path)

    # -- public entry point (thread-safe) ---------------------------------- #
    def dispatch(self, method: str, path: str, body: dict | None) -> ApiResult:
        with self._lock:
            return self._route(method.upper(), path, body or {})

    # -- routing ----------------------------------------------------------- #
    def _route(self, method: str, path: str, body: dict) -> ApiResult:
        if method == "POST" and path == "/api/handle":
            return self._handle(body)
        if method == "POST" and path == "/api/feedback":
            return self._feedback(body)
        if method == "GET" and path == "/api/kpis":
            return ApiResult(200, self.orch.metrics.summary())
        if method == "GET" and path == "/api/learned":
            return ApiResult(200, self._learned())
        if method == "POST" and path == "/api/reset":
            self.orch.reset_state()
            self._save()
            return ApiResult(200, {"ok": True, "message": "Learned state reset to defaults."})
        return ApiResult(404, {"error": f"no route for {method} {path}"})

    # -- handlers ---------------------------------------------------------- #
    def _handle(self, body: dict) -> ApiResult:
        request = str(body.get("request", "")).strip()
        if not request:
            return ApiResult(400, {"error": "missing 'request'"})
        client_id = str(body.get("client_id") or "web-client")
        client_name = str(body.get("client_name") or "there")
        resp = self.orch.handle(request, client_id=client_id, client_name=client_name)
        self._save()
        return ApiResult(
            200,
            {"request": request, "client_id": client_id, "response": resp.model_dump()},
        )

    def _feedback(self, body: dict) -> ApiResult:
        try:
            report = self.orch.improve(self._build_feedback(body))
        except RuntimeError as exc:
            return ApiResult(400, {"error": str(exc)})
        self._save()
        return ApiResult(
            200,
            {
                "evaluation": dataclasses.asdict(report.evaluation),
                "changes": report.all_changes(),
                "metrics": report.metrics,
            },
        )

    @staticmethod
    def _build_feedback(body: dict) -> Feedback:
        return Feedback(
            clicked=body.get("clicked"),
            bought=bool(body.get("bought", False)),
            price_accurate=body.get("price_accurate"),
            comment=str(body.get("comment", "")),
            clicked_listings=list(body.get("clicked_listings") or []),
            ignored_listings=list(body.get("ignored_listings") or []),
        )

    def _learned(self) -> dict:
        cfg = self.orch.config
        return {
            "ranking_weights": cfg.ranking_weights,
            "routing_table": cfg.routing_table,
            "retrieval_config": cfg.retrieval_config,
            "prompt_versions": cfg.prompt_versions,
            "changelog": cfg.changelog,
            "clients": {
                cid: p.model_dump() for cid, p in self.orch.memory.all_clients().items()
            },
        }

    def _save(self) -> None:
        if self.state_path:
            self.orch.save_state(self.state_path)
