"""Real Estate AI Agent Orchestrator with a self-improving Loop Engine.

Phase 1: a multi-agent system (Supervisor + specialized agents).
Phase 2: Loop Engineering — feedback loops that observe, evaluate, adapt,
and improve the system over time.

Public entry point:

    from real_estate_loop import RealEstateOrchestrator
"""
from __future__ import annotations

from .orchestrator import RealEstateOrchestrator

__all__ = ["RealEstateOrchestrator"]
__version__ = "0.1.0"
