"""Client Communication Agent: professional, non-pressuring client messages."""
from __future__ import annotations

from ..core.schemas import CommunicationOutput
from .base import AgentResult, BaseAgent


class ClientCommunicationAgent(BaseAgent):
    name = "ClientCommunicationAgent"

    def _execute(self, task: str, payload: dict) -> AgentResult:
        client_id = payload.get("client_id", "client")
        properties = payload.get("properties", [])  # list of RecommendedProperty-like dicts
        purpose = payload.get("purpose", "share new property recommendations")

        profile = self.ctx.memory.get_client(client_id)
        first_name = payload.get("client_name", "there")

        # Build a clean, factual bullet list (only real, provided listings).
        lines = []
        for p in properties[:3]:
            addr = p.get("address", p.get("property", "a listing"))
            price = p.get("price")
            price_str = f" — ${price:,.0f}" if isinstance(price, (int, float)) and price else ""
            lines.append(f"• {addr}{price_str}")
        bullet_block = "\n".join(lines) if lines else "• (properties to be confirmed)"

        pref_note = ""
        if profile.preferred_locations:
            pref_note = (
                f" I kept your interest in {', '.join(profile.preferred_locations)} in mind."
            )

        fallback = (
            f"Hi {first_name},\n\n"
            f"Following up to {purpose}. Based on what we've discussed, here are a few options "
            f"worth a look:{pref_note}\n\n"
            f"{bullet_block}\n\n"
            f"No pressure at all — if any of these stand out, I'm happy to arrange a tour or send "
            f"more detail. Let me know what works for you.\n\n"
            f"Best regards,\nYour Real Estate Team"
        )
        for directive in self.directives():
            fallback += f"\n\n(P.S. {directive})"

        message = self.narrate(
            system=(
                "You are a professional real estate assistant. Be warm and concise. "
                "Never make legal promises, never pressure the client, never guarantee returns."
            ),
            user="Write a follow-up message to the client.",
            fallback=fallback,
        )

        result = CommunicationOutput(
            message=message,
            recommended_action="Send after broker review; schedule tours for any property the client flags.",
        )
        return AgentResult(
            result=result,
            confidence=0.7,
            next_action="await_broker_approval",
            tools_used=["crm_memory"],
        )
