"""The memory store ties the three memory tiers together.

  * short-term  : rolling conversation buffer per session
  * long-term   : client CRM profiles + broker memory
  * semantic    : (provided separately by the knowledge layer's SemanticIndex)
"""
from __future__ import annotations

from collections import deque

from .broker_memory import BrokerMemory
from .client_memory import ClientProfile


class ShortTermMemory:
    """A small rolling buffer of recent conversation turns per session."""

    def __init__(self, max_turns: int = 12) -> None:
        self.max_turns = max_turns
        self._sessions: dict[str, deque] = {}

    def add(self, session_id: str, role: str, content: str) -> None:
        buf = self._sessions.setdefault(session_id, deque(maxlen=self.max_turns))
        buf.append({"role": role, "content": content})

    def history(self, session_id: str) -> list[dict]:
        return list(self._sessions.get(session_id, []))


class MemoryStore:
    def __init__(self) -> None:
        self.short_term = ShortTermMemory()
        self.broker = BrokerMemory()
        self._clients: dict[str, ClientProfile] = {}

    # -- client profiles ---------------------------------------------------- #
    def get_client(self, client_id: str) -> ClientProfile:
        if client_id not in self._clients:
            self._clients[client_id] = ClientProfile(client_id=client_id)
        return self._clients[client_id]

    def save_client(self, profile: ClientProfile) -> None:
        self._clients[profile.client_id] = profile

    def all_clients(self) -> dict[str, ClientProfile]:
        return dict(self._clients)
