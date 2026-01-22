"""The Loop Engine orchestrates one full improvement cycle.

    Evaluate  ->  Intent  ->  Retrieval  ->  Performance  ->  Memory  ->  Prompt
                  (Loop 1)    (Loop 2)       (Loop 3)         (Loop 4)    (Loop 5)

It mutates the shared RuntimeConfig and MemoryStore in place, so the *next*
request automatically benefits from everything learned in this one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..agents.base import AgentContext
from .evaluation import CycleContext, Evaluation, EvaluationAgent
from .intent_optimizer import IntentOptimizer
from .memory_evolution import MemoryEvolution
from .performance_optimizer import PerformanceOptimizer
from .prompt_optimizer import PromptOptimizer
from .retrieval_optimizer import RetrievalOptimizer


@dataclass
class LoopReport:
    evaluation: Evaluation
    intent_changes: list[str] = field(default_factory=list)
    retrieval_changes: list[str] = field(default_factory=list)
    performance_changes: list[str] = field(default_factory=list)
    memory_changes: list[str] = field(default_factory=list)
    prompt_changes: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def total_changes(self) -> int:
        return sum(
            len(x)
            for x in (
                self.intent_changes,
                self.retrieval_changes,
                self.performance_changes,
                self.memory_changes,
                self.prompt_changes,
            )
        )

    def all_changes(self) -> list[str]:
        out: list[str] = []
        out += [f"[Loop1 Intent] {c}" for c in self.intent_changes]
        out += [f"[Loop2 Retrieval] {c}" for c in self.retrieval_changes]
        out += [f"[Loop3 Performance] {c}" for c in self.performance_changes]
        out += [f"[Loop4 Memory] {c}" for c in self.memory_changes]
        out += [f"[Loop5 Prompt] {c}" for c in self.prompt_changes]
        return out


class LoopEngine:
    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx
        self.evaluator = EvaluationAgent()
        self.intent = IntentOptimizer()
        self.retrieval = RetrievalOptimizer()
        self.performance = PerformanceOptimizer()
        self.memory = MemoryEvolution(ctx.data)
        self.prompt = PromptOptimizer()

    def run_cycle(self, cycle: CycleContext) -> LoopReport:
        config = self.ctx.config
        metrics = self.ctx.metrics
        memory = self.ctx.memory

        # 1) Evaluate the response that just happened.
        evaluation = self.evaluator.evaluate(cycle, memory)

        # 2) Push quality scores back into telemetry + record the response KPIs.
        for agent, quality in evaluation.agent_quality.items():
            metrics.set_quality(agent, quality, feedback=cycle.feedback.comment)
        converted = bool(cycle.feedback.bought or cycle.feedback.clicked)
        metrics.record_response(hallucinated=cycle.hallucinated, converted=converted)

        # 3) Run the five improvement loops in order.
        metadata_before = list(config.retrieval_config.get("metadata_fields", []))

        intent_changes = self.intent.optimize(cycle, evaluation, config)
        retrieval_changes = self.retrieval.optimize(cycle, evaluation, config)
        performance_changes = self.performance.optimize(cycle, evaluation, config, metrics)
        memory_changes = self.memory.evolve(cycle, evaluation, memory, config)
        prompt_changes = self.prompt.optimize(cycle, evaluation, config)

        # 4) If the retrieval metadata changed, rebuild the semantic index.
        metadata_after = list(config.retrieval_config.get("metadata_fields", []))
        if metadata_after != metadata_before:
            self.ctx.semantic.metadata_fields = metadata_after
            self.ctx.semantic.build(self.ctx.data.listings)

        return LoopReport(
            evaluation=evaluation,
            intent_changes=intent_changes,
            retrieval_changes=retrieval_changes,
            performance_changes=performance_changes,
            memory_changes=memory_changes,
            prompt_changes=prompt_changes,
            metrics=metrics.summary(),
        )
