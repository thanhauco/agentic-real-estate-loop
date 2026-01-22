"""Loop 5 — Self-Improvement Loop (versioned prompts).

The "Claude Code loops" idea: Generate -> Execute -> Observe -> Evaluate ->
Modify -> Generate a better version. Here we evolve agent prompt *directives*
(injected into each agent's narration) and bump a version each time.
"""
from __future__ import annotations

from ..core.config import RuntimeConfig
from .evaluation import CycleContext, Evaluation

# Candidate directives the optimizer can add to the Property Search prompt,
# in priority order. Mirrors the spec's v1 -> v2 example (commute, school,
# investment horizon).
_SEARCH_DIRECTIVES = [
    "explicitly weight commute time to the buyer's work hub",
    "factor in school score for family buyers",
    "state the investment horizon assumption (e.g., 5-7 year hold)",
    "call out price-per-square-foot versus neighborhood median",
]


class PromptOptimizer:
    name = "PromptOptimizer"
    ACCURACY_FLOOR = 0.7

    def _bump(self, agent: str, directive: str, config: RuntimeConfig) -> str | None:
        entry = config.prompt_versions.setdefault(agent, {"version": 1, "directives": []})
        if directive in entry["directives"]:
            return None
        entry["directives"].append(directive)
        entry["version"] += 1
        msg = f"{agent} prompt -> v{entry['version']} (added directive: '{directive}')"
        config.log_change(self.name, msg)
        return msg

    def optimize(self, ctx: CycleContext, evaluation: Evaluation, config: RuntimeConfig) -> list[str]:
        changes: list[str] = []
        signals = set(evaluation.signals)

        needs_search_improvement = (
            "weak_retrieval" in signals
            or "low_match_accuracy" in signals
            or evaluation.relevance < self.ACCURACY_FLOOR
            or evaluation.accuracy < self.ACCURACY_FLOOR
        )
        if needs_search_improvement:
            # Add the next not-yet-applied directive (one improvement per cycle).
            current = config.prompt_versions.get("PropertySearchAgent", {}).get("directives", [])
            for directive in _SEARCH_DIRECTIVES:
                if directive not in current:
                    msg = self._bump("PropertySearchAgent", directive, config)
                    if msg:
                        changes.append(msg)
                    break

        # If valuations were judged inaccurate, sharpen the valuation prompt.
        if "low_match_accuracy" in signals and ctx.feedback.price_accurate is False:
            msg = self._bump(
                "ValuationAgent",
                "widen comparable window and report confidence explicitly",
                config,
            )
            if msg:
                changes.append(msg)

        return changes
