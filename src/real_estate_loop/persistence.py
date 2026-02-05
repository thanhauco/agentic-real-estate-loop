"""Persist learned state (config + memory) to disk so it survives restarts.

Only the *learned* state is saved — the things the Loop Engine adapts:

  * RuntimeConfig : ranking weights, routing table, retrieval config,
                    prompt versions, and the change log.
  * MemoryStore   : client CRM profiles and broker memory.

Ephemeral short-term conversation buffers are intentionally NOT persisted.
The semantic index is rebuilt by the caller after restore.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .core.config import (
    DEFAULT_RANKING_WEIGHTS,
    DEFAULT_RETRIEVAL_CONFIG,
    DEFAULT_ROUTING_TABLE,
    RuntimeConfig,
)
from .memory.broker_memory import BrokerMemory, PipelineEntry
from .memory.client_memory import ClientProfile
from .memory.store import MemoryStore

STATE_VERSION = 1


# --------------------------------------------------------------------------- #
# Capture / restore (in-memory <-> plain dict)
# --------------------------------------------------------------------------- #
def capture_state(config: RuntimeConfig, memory: MemoryStore) -> dict:
    """Serialize learned state into a JSON-friendly dict."""
    return {
        "version": STATE_VERSION,
        "config": {
            "ranking_weights": dict(config.ranking_weights),
            "routing_table": {k: list(v) for k, v in config.routing_table.items()},
            "retrieval_config": dict(config.retrieval_config),
            "prompt_versions": copy.deepcopy(config.prompt_versions),
            "changelog": list(config.changelog),
        },
        "clients": {cid: p.model_dump() for cid, p in memory.all_clients().items()},
        "broker": {
            "active_listings": list(memory.broker.active_listings),
            "client_pipeline": [vars(e) for e in memory.broker.client_pipeline],
            "sales_history": list(memory.broker.sales_history),
        },
    }


def restore_state(config: RuntimeConfig, memory: MemoryStore, data: dict) -> None:
    """Apply a captured state dict onto an existing config + memory (in place).

    Mutating in place is important: agents hold references to these objects, so
    we must not replace them.
    """
    cfg = data.get("config", {})
    if "ranking_weights" in cfg:
        config.ranking_weights = dict(cfg["ranking_weights"])
    if "routing_table" in cfg:
        config.routing_table = {k: list(v) for k, v in cfg["routing_table"].items()}
    if "retrieval_config" in cfg:
        config.retrieval_config = dict(cfg["retrieval_config"])
    if "prompt_versions" in cfg:
        config.prompt_versions = copy.deepcopy(cfg["prompt_versions"])
    if "changelog" in cfg:
        config.changelog = list(cfg["changelog"])

    for cid, pdata in data.get("clients", {}).items():
        memory.save_client(ClientProfile.model_validate(pdata))

    broker = data.get("broker", {})
    memory.broker.active_listings = list(broker.get("active_listings", []))
    memory.broker.client_pipeline = [
        PipelineEntry(**entry) for entry in broker.get("client_pipeline", [])
    ]
    memory.broker.sales_history = list(broker.get("sales_history", []))


def reset_state(config: RuntimeConfig, memory: MemoryStore) -> None:
    """Reset config + memory back to factory defaults (in place)."""
    config.ranking_weights = dict(DEFAULT_RANKING_WEIGHTS)
    config.routing_table = copy.deepcopy(DEFAULT_ROUTING_TABLE)
    config.retrieval_config = copy.deepcopy(DEFAULT_RETRIEVAL_CONFIG)
    config.prompt_versions.clear()
    config.changelog.clear()
    memory._clients.clear()  # noqa: SLF001 - intentional internal reset
    memory.broker = BrokerMemory()


# --------------------------------------------------------------------------- #
# File I/O
# --------------------------------------------------------------------------- #
def save_to_file(path: str | Path, config: RuntimeConfig, memory: MemoryStore) -> Path:
    p = Path(path)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(capture_state(config, memory), indent=2), encoding="utf-8")
    return p


def load_from_file(path: str | Path, config: RuntimeConfig, memory: MemoryStore) -> bool:
    """Load state from ``path`` if it exists. Returns True if applied."""
    p = Path(path)
    if not p.exists():
        return False
    data = json.loads(p.read_text(encoding="utf-8"))
    restore_state(config, memory, data)
    return True
