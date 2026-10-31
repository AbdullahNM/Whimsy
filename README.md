# Whimsy — CYOA Engine

A local-first, genre-agnostic **Choose-Your-Own-Adventure (CYOA)** engine. It pairs a deterministic Python orchestration core with a mobile-friendly Progressive Web App (PWA) frontend, and drives narrative turns from structured campaign files instead of a monolithic prompt.

The design goal is simple: every turn is grounded, consequences persist, and no state is ever lost — while the LLM only ever sees the context it needs.

> **Note:** game campaigns (world bibles, gameplay state, turn histories) are private and are **not** included in this repository. A blank `CAMPAIGNS/template_campaign/` is provided as a starting scaffold.

---

## Features

- **Story engine, not a chatbot** — turns are assembled from explicit rules, lore, and state, then persisted.
- **Air-gapped campaigns** — each campaign is a self-contained universe with no cross-references.
- **Dual persistence** — every gameplay record exists as both machine JSON and human-readable Markdown.
- **Rolling context window** — only the latest active turns are fed to the model; older turns auto-archive without data loss.
- **Deterministic state arithmetic** — XP, currency, items, and relations are resolved with explicit, auditable receipts.
- **PWA frontend** — installable, offline-capable UI for reading turns and choosing actions.

---

## Architecture

```
Whimsy/
├── GLOBAL/                  # Authoritative engine rules (single source of truth)
│   ├── CORE-001_HARD_CONSTRAINTS.md
│   ├── CORE-002_TURN_ARCHITECTURE.md
│   ├── CORE-003_ANTI_DEGRADATION.md
│   ├── CAMPAIGN_CONTRACT.md
│   ├── CAMPAIGN_INIT_SPEC.md
│   └── SCHEMAS/             # JSON schemas for campaign init & turn state
├── CAMPAIGNS/
│   └── template_campaign/           # Blank campaign scaffold (real campaigns are private)
├── ENGINE/                  # Python orchestration core
│   ├── engine.py            # Local HTTP server (/generate, /health)
│   ├── prompt_assembler.py  # Builds per-turn context from rules + lore + state
│   ├── state_parser.py      # Parses XP / currency / SYS receipts
│   └── turn_archiver.py     # Rolls old turns from ACTIVE/ into ARCHIVE/
├── UI/                      # Installable PWA frontend
├── openspec/                # Formal engine specifications & change proposals
├── REVIEWS/                 # Architecture and UX review notes
├── tests/                   # Python + Node test suites
├── AGENTS.md                # Agent/GM operating protocol
└── INDEX.md                 # Full documentation index
```

### Campaign layout

Each campaign under `CAMPAIGNS/<campaign_id>/` follows a fixed shape:

```
<campaign_id>/
├── campaign_config.json   # Theme, metrics, HUD definition
├── CONFIG.yaml            # Model / temperature / context budgets
├── GAMEPLAY/              # status, items, relations (JSON + Markdown)
├── IDEAS/                 # narrative_steering.md — long-term arcs
├── WORLD_BIBLE/           # CORE, PLACES, PEOPLE, FACTIONS, GUIDES
└── TURNS/                 # ACTIVE/ (rolling window) + ARCHIVE/ (full history)
```

---

## Getting started

Requirements: **Python 3.10+** and **Node.js 18+** (Node is only needed for the JS test suite).

### Run the engine server

```bash
python3 ENGINE/engine.py
# listens on http://localhost:8000 (override with ANTIGRAVITY_PORT)
```

Endpoints:

| Method | Path       | Purpose                                              |
|--------|------------|------------------------------------------------------|
| `GET`  | `/health`  | Status + active campaign diagnostics                 |
| `POST` | `/generate`| Process a player choice and return the next GM turn  |

### Run the PWA

```bash
python3 -m http.server 3000 --directory UI
# open http://localhost:3000
```

### Run the tests

```bash
bash tests/run_all_tests.sh
```

This runs the Python `unittest` suite, the Node `--test` suites, and (if the `openspec` CLI is installed) validates the specifications.

---

## Creating a campaign

1. Copy `CAMPAIGNS/template_campaign/` to `CAMPAIGNS/<your_campaign_id>/`.
2. Fill in `campaign_config.json` and `CONFIG.yaml`.
3. Populate `WORLD_BIBLE/` and `GAMEPLAY/`.
4. Start the engine and UI; the prompt assembler handles the rest.

See `GLOBAL/CAMPAIGN_INIT_SPEC.md` for the full contract.

---

## Documentation

- `INDEX.md` — architecture and directory reference
- `GLOBAL/` — the authoritative rules every turn must follow
- `openspec/specs/` — formal specs for the persistence contract, campaign schema, UI renderer, and local engine
- `AGENTS.md` — the GM/agent operating protocol

---

## Status

Early but functional. The engine core, PWA shell, persistence layer, and test suites are in place; campaign content is supplied separately.

---

## License

Released under the [MIT License](LICENSE).
