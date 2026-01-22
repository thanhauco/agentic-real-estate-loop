"""Phase 2 — Loop Engineering.

A system of feedback loops that observe, evaluate, adapt, and improve the
multi-agent system over time:

  Loop 1  Intent Optimization      -> routing
  Loop 2  Retrieval Improvement    -> RAG / semantic params
  Loop 3  Agent Performance        -> ranking weights
  Loop 4  Memory Evolution         -> learned client profiles
  Loop 5  Self-Improvement         -> versioned prompts
"""
from __future__ import annotations

from .evaluation import CycleContext, EvaluationAgent, Evaluation, Feedback
from .intent_optimizer import IntentOptimizer
from .loop_engine import LoopEngine, LoopReport
from .memory_evolution import MemoryEvolution
from .performance_optimizer import PerformanceOptimizer
from .prompt_optimizer import PromptOptimizer
from .retrieval_optimizer import RetrievalOptimizer

__all__ = [
    "CycleContext",
    "EvaluationAgent",
    "Evaluation",
    "Feedback",
    "IntentOptimizer",
    "LoopEngine",
    "LoopReport",
    "MemoryEvolution",
    "PerformanceOptimizer",
    "PromptOptimizer",
    "RetrievalOptimizer",
]
