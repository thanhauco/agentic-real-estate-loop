"""Interactive command-line interface for the Real Estate AI system.

A broker can drive the full loop from a terminal:

    request           -> Supervisor + agents answer (Phase 1)
    :feedback ...     -> the Loop Engine learns from the outcome (Phase 2)
    :kpis / :learned  -> inspect telemetry and what the system adapted

Zero-install entry points:
    python realestate.py                 (repo-root launcher)
    python -m real_estate_loop           (when installed or PYTHONPATH=src)
    realestate                           (console script after `pip install -e .`)
"""
from __future__ import annotations

import argparse
import re
import sys

from .loops.evaluation import Feedback
from .orchestrator import RealEstateOrchestrator

_MLS_RE = re.compile(r"MLS-\d+", re.IGNORECASE)

BANNER = "Real Estate AI — Orchestrator & Loop Engine (type :help, :quit to exit)"

HELP = """commands:
  <request>                 ask the broker assistant (e.g. "$700k investment house near Seattle")
  :feedback <text>          teach the loops from the last answer
                            keywords: bought | clicked MLS-#### | ignored MLS-#### | price-wrong
  :client <id>              switch the active client (memory is per-client)
  :kpis                     show telemetry / business KPIs
  :learned                  show what the loops have adapted so far
  :save                     persist learned state to disk now
  :reset                    reset learned state back to factory defaults
  :help                     show this help
  :quit                     exit"""


class BrokerCLI:
    """Stateful command processor. ``handle_command`` is pure of I/O for testing."""

    def __init__(
        self,
        orch: RealEstateOrchestrator | None = None,
        client_id: str = "broker-client",
        state_path: str | None = None,
    ) -> None:
        self.orch = orch or RealEstateOrchestrator()
        self.client_id = client_id
        self.state_path = state_path
        self.has_turn = False

    # -- command dispatch --------------------------------------------------- #
    def handle_command(self, line: str) -> str | None:
        """Return output text, '' for no-op, or None to signal exit."""
        line = (line or "").strip()
        if not line:
            return ""
        if line in (":quit", ":exit", ":q"):
            return None
        if line in (":help", ":h", "help"):
            return HELP
        if line == ":kpis":
            return self._format_kpis()
        if line == ":learned":
            return self._format_learned()
        if line == ":save":
            return self._save_state()
        if line == ":reset":
            return self._reset_state()
        if line.startswith(":client"):
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                self.client_id = parts[1].strip()
                return f"Active client set to '{self.client_id}'."
            return "usage: :client <id>"
        if line.startswith(":feedback"):
            return self._apply_feedback(line[len(":feedback"):].strip())
        if line.startswith(":"):
            return f"Unknown command '{line}'. Type :help."
        return self._handle_request(line)

    # -- request -> answer -------------------------------------------------- #
    def _handle_request(self, request: str) -> str:
        resp = self.orch.handle(request, client_id=self.client_id)
        self.has_turn = True
        lines = [resp.executive_summary]

        if resp.uncertain:
            lines.append(f"  ! uncertain: {resp.uncertain.reason}")
            lines.append(f"    need: {', '.join(resp.uncertain.required_information)}")
            return "\n".join(lines)

        if resp.recommended_properties:
            lines.append("Recommended:")
            for i, p in enumerate(resp.recommended_properties[:3], 1):
                est = f"  est {p.estimated_value}" if p.estimated_value else ""
                lines.append(f"  {i}. {p.address} [{p.property}]  ${p.price:,.0f}  match {p.match_score:.0f}/100{est}")
        if resp.market_analysis:
            lines.append(f"Market: investment score {resp.market_analysis.investment_score}/100, "
                         f"trend {resp.market_analysis.price_trend}")
        if resp.follow_up_tasks:
            lines.append(f"Follow-ups: {resp.follow_up_tasks[0]}"
                         + (f" (+{len(resp.follow_up_tasks) - 1} more)" if len(resp.follow_up_tasks) > 1 else ""))
        if resp.warnings:
            lines.append(f"  ! {resp.warnings[0]}")
        lines.append(f"agents: {', '.join(resp.agents_used) or '(none)'}   "
                     f"(tip: ':feedback ...' to teach the loops)")
        return "\n".join(lines)

    # -- feedback -> learning ---------------------------------------------- #
    def _apply_feedback(self, text: str) -> str:
        if not self.has_turn:
            return "No prior response to give feedback on — make a request first."
        report = self.orch.improve(self._parse_feedback(text))
        ev = report.evaluation
        out = [f"evaluation: overall {ev.overall:.2f} (relevance {ev.relevance:.2f}, "
               f"completeness {ev.completeness:.2f}, accuracy {ev.accuracy:.2f})"]
        changes = report.all_changes()
        if changes:
            out.append(f"the system adapted ({len(changes)}):")
            out.extend(f"  - {c}" for c in changes)
        else:
            out.append("no adaptations needed this time.")
        return "\n".join(out)

    @staticmethod
    def _parse_feedback(text: str) -> Feedback:
        low = text.lower()
        ids = [i.upper() for i in _MLS_RE.findall(text)]
        fb = Feedback(comment=text)
        if "bought" in low or "offer" in low or "purchased" in low:
            fb.bought = True
            fb.clicked = True
        if "price-wrong" in low or "inaccurate" in low or "wrong price" in low:
            fb.price_accurate = False
        if "ignored" in low or "skip" in low:
            fb.ignored_listings = ids
        elif ids or "clicked" in low or "liked" in low:
            fb.clicked = True
            fb.clicked_listings = ids
        return fb

    # -- inspectors --------------------------------------------------------- #
    def _format_kpis(self) -> str:
        return "KPIs:\n" + "\n".join(
            f"  {k:22}: {v}" for k, v in self.orch.metrics.summary().items()
        )

    def _save_state(self) -> str:
        if not self.state_path:
            return "Persistence is disabled (omit --no-persist to enable)."
        path = self.orch.save_state(self.state_path)
        return f"Saved learned state to {path}."

    def _reset_state(self) -> str:
        self.orch.reset_state()
        if self.state_path:
            self.orch.save_state(self.state_path)
        return "Learned state reset to factory defaults."

    def _format_learned(self) -> str:
        cfg = self.orch.config
        profile = self.orch.memory.get_client(self.client_id)
        lines = [
            f"adaptations logged : {len(cfg.changelog)}",
            f"routing(investment): {cfg.routing_table.get('investment')}",
            f"ranking weights    : {cfg.ranking_weights}",
            f"retrieval config   : {cfg.retrieval_config}",
            f"client '{self.client_id}': locations={profile.preferred_locations}, "
            f"dislikes={profile.dislikes}, confidence={profile.confidence}",
        ]
        if cfg.prompt_versions:
            for agent, info in cfg.prompt_versions.items():
                lines.append(f"prompt {agent} -> v{info['version']}")
        return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="real_estate_loop", description=BANNER)
    parser.add_argument("--client", default="broker-client", help="active client id")
    parser.add_argument("--once", metavar="REQUEST", help="process a single request and exit")
    parser.add_argument(
        "--state",
        default=".realestate_state.json",
        help="path to the learned-state file (default: .realestate_state.json)",
    )
    parser.add_argument(
        "--no-persist", action="store_true", help="do not load or save learned state"
    )
    args = parser.parse_args(argv)

    persist = not args.no_persist
    state_path = args.state if persist else None
    cli = BrokerCLI(client_id=args.client, state_path=state_path)

    restored = bool(state_path and cli.orch.load_state(state_path))

    if args.once:
        # One-shot: benefit from prior learning, but don't write state back.
        out = cli.handle_command(args.once)
        if out:
            print(out)
        return 0

    print(BANNER)
    if restored:
        print(f"(restored learned state from {state_path})")
    interactive = sys.stdin.isatty()
    if interactive:
        print(HELP)
    while True:
        if interactive:
            try:
                line = input("broker> ")
            except EOFError:
                break
        else:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.rstrip("\n")
            if line.strip():
                print(f"broker> {line}")
        out = cli.handle_command(line)
        if out is None:
            break
        if out:
            print(out)
        # Auto-save after each command so learning is durable even on a hard exit.
        if state_path and line.strip():
            cli.orch.save_state(state_path)
    if state_path:
        cli.orch.save_state(state_path)
        print(f"State saved to {state_path}.")
    print("Goodbye.")
    return 0
