# Architecture

This document explains how the **Real Estate AI Agent Orchestrator** (Phase 1)
and the **Loop Engine** (Phase 2) fit together, with diagrams for the system
context, components, request lifecycle, the five improvement loops, memory,
and state persistence.

> All diagrams are Mermaid and render on GitHub and in VS Code.

---

## 1. System context

A broker interacts with one system that reads from real-estate data sources,
optionally calls an LLM to polish narrative text, and persists what it learns.

```mermaid
flowchart TD
    Broker([Real Estate Broker]) -->|requests + feedback| Sys
    subgraph Sys[Real Estate AI System]
        Orc[Orchestrator]
        Loop[Loop Engine]
    end
    Sys -->|reads| MLS[(MLS / Listings)]
    Sys -->|reads| MKT[(Market Data)]
    Sys -->|reads| CMP[(Comparable Sales)]
    Sys -.optional.-> LLM{{LLM Provider<br/>OpenAI / Azure}}
    Sys -->|persists learning| Disk[(State file JSON)]
```

The data sources are the **single source of truth**. The anti-hallucination
guardrail only permits the system to reference listing ids that exist there.

---

## 2. Components

The codebase is layered. Agents read from the knowledge and memory layers and
emit telemetry; the Loop Engine writes to the shared `RuntimeConfig` and
`MemoryStore` that the agents read on the next request.

```mermaid
flowchart TB
    subgraph API[Entry points]
        CLI[CLI / REPL]
        PY[Python API]
    end
    API --> ORCH[Orchestrator]
    ORCH --> SUP[Supervisor]
    ORCH --> VAL[Response Validator]
    ORCH --> LE[Loop Engine]
    subgraph Agents
        PS[PropertySearch]
        MI[MarketIntelligence]
        VALU[Valuation]
        CC[Communication]
        DR[DocumentReview]
    end
    SUP --> Agents
    subgraph Knowledge
        DS[DataSources]
        SI[SemanticIndex]
    end
    subgraph Memory
        STM[ShortTerm]
        CM[ClientProfiles]
        BM[BrokerMemory]
    end
    Agents --> Knowledge
    Agents --> Memory
    Agents --> TEL[Telemetry]
    LE --> CFG[(RuntimeConfig)]
    LE --> Memory
    CFG --> Agents
```

| Layer | Module | Responsibility |
|---|---|---|
| Core | `core/` | schemas, `RuntimeConfig`, LLM client, guardrails |
| Knowledge | `knowledge/` | data sources (MLS/market/comps), TF-IDF semantic index |
| Memory | `memory/` | short-term buffer, client CRM profiles, broker memory |
| Telemetry | `telemetry/` | latency, tokens, success/hallucination/conversion rates |
| Agents | `agents/` | supervisor, 5 specialized agents, response validator |
| Loops | `loops/` | evaluation agent, 5 loops, loop engine |
| Entry | `orchestrator.py`, `cli.py` | `handle` / `improve` / `process`, REPL |

---

## 3. Phase 1 — request lifecycle

`orchestrator.handle()` plans the work, runs the needed agents in a sensible
order, then passes everything through the validator before responding.

```mermaid
sequenceDiagram
    actor Broker
    participant O as Orchestrator
    participant S as Supervisor
    participant PS as PropertySearch
    participant MI as MarketIntelligence
    participant V as Valuation
    participant RV as Validator
    Broker->>O: handle(request)
    O->>S: plan(request)
    S-->>O: intents + buyer + agents
    O->>PS: rank listings
    PS-->>O: PropertyMatch[]
    O->>MI: analyze market
    MI-->>O: MarketSummary
    O->>V: value top matches
    V-->>O: Valuation[]
    O->>RV: validate(response)
    RV-->>O: ok / warnings / hallucination
    O-->>Broker: FinalResponse
```

Which agents run is decided by the **routing table** in `RuntimeConfig`, keyed
by detected intent. The Property Search ranking is a weighted blend:

```mermaid
pie showData title Property Search ranking weights (defaults)
    "Requirements (budget, beds, type)" : 40
    "Location + commute" : 30
    "Investment value" : 20
    "Market timing" : 10
```

These weights live in config so Loop 3 can retune them from feedback.

---

## 4. Phase 2 — Loop Engineering

After each response (and any feedback) the Loop Engine evaluates the outcome
and runs five loops that adapt the shared state, so the **next** request is
already better.

```mermaid
flowchart LR
    R([Response + Feedback]) --> E[Evaluation Agent]
    E --> L1[Loop 1 Intent]
    E --> L2[Loop 2 Retrieval]
    E --> L3[Loop 3 Performance]
    E --> L4[Loop 4 Memory]
    E --> L5[Loop 5 Prompt]
    L1 & L2 & L3 & L4 & L5 --> CFG[(RuntimeConfig + Memory)]
    CFG --> N([Next request improves])
```

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant LE as LoopEngine
    participant EA as EvaluationAgent
    participant CFG as RuntimeConfig
    participant MEM as MemoryStore
    O->>LE: run_cycle(context, feedback)
    LE->>EA: evaluate(response, feedback)
    EA-->>LE: scores + signals
    LE->>CFG: intent / retrieval / performance / prompt updates
    LE->>MEM: memory evolution (client profile)
    LE-->>O: LoopReport (what changed)
```

| Loop | Reads (signals) | Writes |
|---|---|---|
| 1 Intent | `missing_market_analysis`, `missing_valuation` | routing table |
| 2 Retrieval | `weak_retrieval`, low relevance | `top_k`, rerank, metadata, version |
| 3 Performance | `ranking_mismatch_*`, low quality | ranking weights |
| 4 Memory | clicked / ignored listings | client profile (likes, dislikes, confidence) |
| 5 Prompt | `weak_retrieval`, `low_match_accuracy` | versioned prompt directives |

---

## 5. Memory tiers

```mermaid
flowchart TD
    subgraph ST[Short-term]
        CONV[Conversation buffer per session]
    end
    subgraph LT[Long-term CRM]
        CP[Client Profiles<br/>prefs · dislikes · confidence]
        BR[Broker Memory<br/>listings · pipeline · sales]
    end
    subgraph SEM[Semantic]
        IDX[TF-IDF index over listings]
    end
    CONV --> CP
    CP --> BR
    IDX -.serves.-> CP
```

A client moves through the broker pipeline as deals progress:

```mermaid
stateDiagram-v2
    [*] --> new
    new --> nurturing
    nurturing --> touring
    touring --> offer
    offer --> closed
    offer --> lost
    nurturing --> lost
    closed --> [*]
    lost --> [*]
```

---

## 6. Data model

```mermaid
erDiagram
    NEIGHBORHOOD ||--o{ LISTING : contains
    NEIGHBORHOOD ||--|| MARKET : has
    LISTING ||--o{ COMPARABLE : "valued against"
    LISTING {
        string id PK
        string neighborhood
        float price
        string property_type
        int bedrooms
    }
    MARKET {
        float median_price
        float yoy_appreciation
        float months_inventory
        float gross_rent_yield
    }
    COMPARABLE {
        string address
        float sold_price
        int sqft
    }
```

---

## 7. State persistence

The CLI persists the **learned** state (config knobs + memory) to a JSON file
and restores it on startup, so adaptations survive restarts. Ephemeral
short-term conversation buffers are intentionally not persisted.

```mermaid
flowchart LR
    Start([CLI start]) -->|load_state| File[(state.json)]
    File --> Cfg[RuntimeConfig + Memory restored]
    Cfg --> Run[answer + learn]
    Run -->|save_state after each cycle| File
    Run --> Exit([CLI exit])
    Exit -->|save_state| File
```

What is persisted:

- **Config**: ranking weights, routing table, retrieval config, prompt
  versions, and the change log.
- **Memory**: client profiles (preferences, dislikes, behavior signals,
  confidence) and broker memory (active listings, pipeline, sales history).

On load, the semantic index is rebuilt to match the restored retrieval metadata
fields.

---

## See also

- [README.md](../README.md) — quickstart, agent contracts, production-stack mapping
- `src/real_estate_loop/orchestrator.py` — top-level wiring
- `src/real_estate_loop/loops/loop_engine.py` — the five loops in order
