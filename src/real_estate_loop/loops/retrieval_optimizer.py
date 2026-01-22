"""Loop 2 — Retrieval Improvement Loop.

When evaluation shows the knowledge layer returned thin or weak results, this
loop widens retrieval, enables reranking, and enriches the searchable metadata,
then bumps a config version so the change is auditable.
"""
from __future__ import annotations

from ..core.config import RuntimeConfig
from .evaluation import CycleContext, Evaluation


class RetrievalOptimizer:
    name = "RetrievalOptimizer"
    MAX_TOP_K = 10

    def optimize(self, ctx: CycleContext, evaluation: Evaluation, config: RuntimeConfig) -> list[str]:
        changes: list[str] = []
        signals = set(evaluation.signals)
        rc = config.retrieval_config

        weak = "weak_retrieval" in signals or evaluation.relevance < 0.6

        if weak:
            old_k = int(rc.get("top_k", 5))
            new_k = min(self.MAX_TOP_K, old_k + 2)
            if new_k != old_k:
                rc["top_k"] = new_k
                msg = f"top_k {old_k} -> {new_k} (weak retrieval / low relevance)"
                config.log_change(self.name, msg)
                changes.append(msg)

            if not rc.get("rerank", False):
                rc["rerank"] = True
                msg = "enabled reranking of retrieved listings"
                config.log_change(self.name, msg)
                changes.append(msg)

            if "description" not in rc.get("metadata_fields", []):
                rc.setdefault("metadata_fields", []).append("description")
                msg = "added 'description' to indexed metadata fields"
                config.log_change(self.name, msg)
                changes.append(msg)

        if changes:
            rc["version"] = int(rc.get("version", 1)) + 1
            changes.append(f"retrieval config version -> {rc['version']}")

        return changes
