"""Top-level Real Estate AI Agent Orchestrator.

Phase 1:  ``handle(request)``  -> runs the Supervisor + specialized agents +
          the Response Validator and returns a structured FinalResponse.

Phase 2:  ``improve(feedback)`` -> runs the Loop Engine over the last response
          to adapt routing, ranking, retrieval, memory, and prompts.

          ``process(request, feedback=...)`` does both in one call.

Runs fully offline by default (deterministic mock LLM). Set provider env vars
to use a real model for narrative polishing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .agents.base import AgentContext
from .agents.communication import ClientCommunicationAgent
from .agents.document_review import DocumentReviewAgent
from .agents.market_intelligence import MarketIntelligenceAgent
from .agents.property_search import PropertySearchAgent
from .agents.supervisor import SupervisorAgent, SupervisorPlan
from .agents.validator import ResponseValidator
from .agents.valuation import ValuationAgent
from .core.config import RuntimeConfig
from .core.guardrails import uncertain
from .core.llm import LLMClient
from .core.schemas import (
    AgentMessage,
    BuyerProfile,
    FinalResponse,
    Intent,
    MarketSummary,
    PropertyMatch,
    RecommendedProperty,
    Valuation,
)
from .knowledge.data_sources import DataSources
from .knowledge.vector_store import SemanticIndex
from .loops.evaluation import CycleContext, Feedback
from .loops.loop_engine import LoopEngine, LoopReport
from .memory.store import MemoryStore
from .persistence import load_from_file, reset_state, save_to_file
from .telemetry.metrics import MetricsCollector

_MLS_RE = re.compile(r"MLS-\d{3,}", re.IGNORECASE)


@dataclass
class _CycleState:
    """Internal record of the last response, used by ``improve``."""

    request: str
    plan: SupervisorPlan
    agent_messages: list[AgentMessage]
    response: FinalResponse
    hallucinated: bool
    client_id: str
    candidate_count: int


class RealEstateOrchestrator:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.llm = LLMClient()
        self.data = DataSources(data_dir)
        self.memory = MemoryStore()
        self.metrics = MetricsCollector()
        self.config = RuntimeConfig()
        self.semantic = SemanticIndex(
            self.data.listings,
            metadata_fields=list(self.config.retrieval_config["metadata_fields"]),
        )
        self.ctx = AgentContext(
            llm=self.llm,
            data=self.data,
            memory=self.memory,
            metrics=self.metrics,
            config=self.config,
            semantic=self.semantic,
        )
        self.supervisor = SupervisorAgent(self.data, self.config)
        self.validator = ResponseValidator(self.data.all_listing_ids())
        self.loop_engine = LoopEngine(self.ctx)
        self.agents = {
            PropertySearchAgent.name: PropertySearchAgent(self.ctx),
            MarketIntelligenceAgent.name: MarketIntelligenceAgent(self.ctx),
            ValuationAgent.name: ValuationAgent(self.ctx),
            ClientCommunicationAgent.name: ClientCommunicationAgent(self.ctx),
            DocumentReviewAgent.name: DocumentReviewAgent(self.ctx),
        }
        self._last: _CycleState | None = None

    # ------------------------------------------------------------------ #
    # PHASE 1 — handle a broker request
    # ------------------------------------------------------------------ #
    def handle(
        self,
        request: str,
        client_id: str = "anon",
        client_name: str = "there",
        document_text: str | None = None,
        document_type: str | None = None,
    ) -> FinalResponse:
        plan = self.supervisor.plan(request)
        self.memory.short_term.add(client_id, "user", request)

        # Merge any learned client preferences into the buyer profile.
        profile = self.memory.get_client(client_id)
        buyer = plan.buyer_profile
        if profile.preferred_locations and not buyer.location:
            buyer.location = profile.preferred_locations[0]
        buyer.preferences = list({*buyer.preferences, *profile.to_buyer_preferences()})

        # Guardrail: bail out gracefully when we lack the basics to search.
        wants_search = Intent.SEARCH in plan.intents or Intent.INVESTMENT in plan.intents
        if wants_search and not buyer.budget and not buyer.location and not buyer.property_type:
            unc = uncertain(
                reason="Not enough buyer criteria to search responsibly.",
                required_information=["budget", "preferred location", "property type or bedrooms"],
            )
            resp = FinalResponse(
                executive_summary="I need a little more to go on before recommending listings.",
                uncertain=unc,
                agents_used=[],
                follow_up_tasks=["Collect budget, location, and property type from the client"],
            )
            self._remember_cycle(request, plan, [], resp, False, client_id, 0)
            return resp

        agent_messages: list[AgentMessage] = []
        search_matches: list[PropertyMatch] = []
        market: MarketSummary | None = None
        valuations: dict[str, Valuation] = {}
        candidate_count = 0

        # 1) Property search
        if PropertySearchAgent.name in plan.agents:
            msg = self.agents[PropertySearchAgent.name].run("find_matching_properties", buyer)
            agent_messages.append(msg)
            search_matches = msg.result or []
            candidate_count = len(search_matches)
            for m in search_matches[:3]:
                profile.record_view(m.property)

        # 2) Market intelligence
        if MarketIntelligenceAgent.name in plan.agents:
            msg = self.agents[MarketIntelligenceAgent.name].run(
                "analyze_market", {"neighborhoods": plan.target_neighborhoods}
            )
            agent_messages.append(msg)
            market = msg.result

        # 3) Valuation — value top matches and/or explicitly referenced listings.
        if ValuationAgent.name in plan.agents:
            ids = [m.property for m in search_matches[:3]]
            for explicit in _MLS_RE.findall(request):
                explicit = explicit.upper()
                if explicit not in ids:
                    ids.insert(0, explicit)
            for lid in ids[:3]:
                msg = self.agents[ValuationAgent.name].run("estimate_value", {"property_id": lid})
                agent_messages.append(msg)
                if msg.result:
                    valuations[lid] = msg.result

        # Assemble recommended properties (search matches enriched with valuation).
        recommended = self._assemble_recommendations(search_matches, valuations)

        # 4) Client communication (uses the recommendations we just built)
        if ClientCommunicationAgent.name in plan.agents:
            msg = self.agents[ClientCommunicationAgent.name].run(
                "draft_followup",
                {
                    "client_id": client_id,
                    "client_name": client_name,
                    "properties": [r.model_dump() for r in recommended],
                    "purpose": "share new property recommendations",
                },
            )
            agent_messages.append(msg)
            comm_action = msg.result.recommended_action if msg.result else ""
        else:
            comm_action = ""

        # 5) Document review
        doc_review = None
        if DocumentReviewAgent.name in plan.agents or document_text:
            agent = self.agents[DocumentReviewAgent.name]
            msg = agent.run(
                "review_document",
                {"document_type": document_type or "document", "text": document_text or ""},
            )
            agent_messages.append(msg)
            doc_review = msg.result

        response = self._build_final_response(
            plan, recommended, market, doc_review, comm_action
        )

        # Validate (quality gate + anti-hallucination), then prune fabrications.
        validation = self.validator.validate(response, agent_messages)
        if validation.hallucinated:
            known = self.data.all_listing_ids()
            response.recommended_properties = [
                r for r in response.recommended_properties if r.property in known
            ]
        response.warnings = validation.warnings

        self.memory.save_client(profile)
        self.memory.short_term.add(client_id, "assistant", response.executive_summary)
        self._remember_cycle(
            request, plan, agent_messages, response, validation.hallucinated, client_id, candidate_count
        )
        return response

    # ------------------------------------------------------------------ #
    # PHASE 2 — improve from feedback
    # ------------------------------------------------------------------ #
    def improve(self, feedback: Feedback | None = None) -> LoopReport:
        if self._last is None:
            raise RuntimeError("Call handle(...) before improve(...).")
        state = self._last
        cycle = CycleContext(
            request=state.request,
            intents=state.plan.intents,
            buyer=state.plan.buyer_profile,
            agent_messages=state.agent_messages,
            response=state.response,
            hallucinated=state.hallucinated,
            client_id=state.client_id,
            feedback=feedback or Feedback(),
            candidate_count=state.candidate_count,
        )
        return self.loop_engine.run_cycle(cycle)

    def process(
        self, request: str, client_id: str = "anon", feedback: Feedback | None = None, **kwargs
    ) -> tuple[FinalResponse, LoopReport]:
        response = self.handle(request, client_id=client_id, **kwargs)
        report = self.improve(feedback)
        return response, report

    # ------------------------------------------------------------------ #
    # State persistence — learned config + memory survive restarts
    # ------------------------------------------------------------------ #
    def save_state(self, path: str | Path = "realestate_state.json") -> str:
        """Persist learned config + memory to ``path``. Returns the path written."""
        return str(save_to_file(path, self.config, self.memory))

    def load_state(self, path: str | Path = "realestate_state.json") -> bool:
        """Restore learned config + memory from ``path`` if it exists."""
        loaded = load_from_file(path, self.config, self.memory)
        if loaded:
            self._rebuild_semantic_index()
        return loaded

    def reset_state(self) -> None:
        """Reset learned config + memory back to factory defaults (in place)."""
        reset_state(self.config, self.memory)
        self._rebuild_semantic_index()

    def _rebuild_semantic_index(self) -> None:
        """Rebuild the semantic index to match the (possibly restored) metadata."""
        self.semantic.metadata_fields = list(
            self.config.retrieval_config.get("metadata_fields", self.semantic.metadata_fields)
        )
        self.semantic.build(self.data.listings)

    # ------------------------------------------------------------------ #
    # Assembly helpers
    # ------------------------------------------------------------------ #
    def _assemble_recommendations(
        self, matches: list[PropertyMatch], valuations: dict[str, Valuation]
    ) -> list[RecommendedProperty]:
        recs: list[RecommendedProperty] = []
        for m in matches[:5]:
            val = valuations.get(m.property)
            recs.append(
                RecommendedProperty(
                    property=m.property,
                    address=m.address,
                    price=m.price,
                    match_score=m.match_score,
                    reason=m.reason,
                    concerns=m.concerns,
                    estimated_value=val.estimated_value if val else None,
                    negotiation_strategy=val.negotiation_strategy if val else None,
                )
            )
        return recs

    def _build_final_response(
        self,
        plan: SupervisorPlan,
        recommended: list[RecommendedProperty],
        market: MarketSummary | None,
        doc_review,
        comm_action: str,
    ) -> FinalResponse:
        # Executive summary
        if recommended:
            top = recommended[0]
            summary_seed = (
                f"Found {len(recommended)} strong match(es). Top pick: {top.address} "
                f"(match {top.match_score:.0f}/100, ${top.price:,.0f})."
            )
        elif market:
            summary_seed = (
                f"Market analysis complete with an investment score of "
                f"{market.investment_score}/100."
            )
        elif doc_review:
            summary_seed = f"Reviewed a {doc_review.document_type}; see flagged items below."
        else:
            summary_seed = "Request processed."
        if market and recommended:
            summary_seed += f" Market investment score: {market.investment_score}/100."

        executive_summary = self.agents[PropertySearchAgent.name].narrate(
            system="You are the Supervisor summarizing a multi-agent result for a broker.",
            user="Write a 1-2 sentence executive summary.",
            fallback=summary_seed,
        )

        # Client action plan
        action_plan: list[str] = []
        for r in recommended[:3]:
            action_plan.append(f"Review {r.address} (match {r.match_score:.0f}/100) with the client")
        if recommended:
            action_plan.append("Shortlist 2-3 favorites and schedule tours")
            action_plan.append("Start mortgage pre-approval to strengthen offers")
        if market and market.risks:
            action_plan.append(f"Discuss market risks: {market.risks[0]}")
        if doc_review and doc_review.attorney_review_required:
            action_plan.append(f"Route to attorney: {doc_review.attorney_review_required[0]}")

        # Follow-up tasks
        follow_ups: list[str] = []
        if comm_action:
            follow_ups.append(comm_action)
        if recommended:
            follow_ups.append("Send the recommendation email after broker review")
            follow_ups.append("Refresh comparable sales before submitting any offer")
        if doc_review:
            follow_ups.extend(f"Attorney review: {item}" for item in doc_review.attorney_review_required[:2])
        if not follow_ups:
            follow_ups.append("Await client response")

        return FinalResponse(
            executive_summary=executive_summary,
            recommended_properties=recommended,
            market_analysis=market,
            client_action_plan=action_plan,
            follow_up_tasks=follow_ups,
            agents_used=plan.agents,
        )

    def _remember_cycle(
        self,
        request: str,
        plan: SupervisorPlan,
        agent_messages: list[AgentMessage],
        response: FinalResponse,
        hallucinated: bool,
        client_id: str,
        candidate_count: int,
    ) -> None:
        self._last = _CycleState(
            request=request,
            plan=plan,
            agent_messages=agent_messages,
            response=response,
            hallucinated=hallucinated,
            client_id=client_id,
            candidate_count=candidate_count,
        )
