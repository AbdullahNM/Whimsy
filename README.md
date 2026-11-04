# Whimsy — CYOA Engine

A local-first, genre-agnostic **Choose-Your-Own-Adventure (CYOA)** engine. It pairs a deterministic Python orchestration core with a mobile-friendly Progressive Web App (PWA) frontend, and drives narrative turns from structured campaign files instead of a monolithic prompt.

The design goal is simple: every turn is grounded, consequences persist, and no state is ever lost — while the LLM only ever sees the context it needs.

> **Note:** game campaigns (world bibles, gameplay state, turn histories) are private and are **not** included in this repository. A blank `CAMPAIGNS/template_campaign/` is provided as a starting scaffold.

---

## Features

- **Story engine, not a chatbot** — turns are assembled from explicit rules, lore, and state, then persisted.
- **Dual operational modes** — deterministic **Classic CYOA** (strict option validation) and emergent **Freeform Simulation** (compound prose actions).
- **Air-gapped campaigns** — each campaign is a self-contained universe with no cross-references.
- **Dual persistence** — every gameplay record exists as both machine JSON and human-readable Markdown.
- **Transactional state commits** — two-phase atomic state updates with deterministic idempotency tokens.
- **Adaptive narrative focus** — dynamic camera zoom (`detailed_scene`, `short_summary`, `montage`, `time_skip`) and anti-degradation transition gates.
- **Persistent style contracts** — automated linter enforcing natural, grounded English with zero narrative drift.
- **World-first sandboxing** — epistemic separation of immutable facts, autonomous factions, and canon secrets.
- **Rolling context window** — only the latest active turns are fed to the model; older turns auto-archive without data loss.
- **PWA frontend** — installable, offline-capable UI with real-time HUD (Operational Mode badge, Focus pill, Simulation Clock).

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
│   └── template_campaign/   # Blank campaign scaffold (real campaigns are private)
├── ENGINE/                  # Python orchestration core
│   ├── engine.py            # Local HTTP server (/generate, /health)
│   ├── mode_validator.py    # Deterministic mode validation (classic vs freeform)
│   ├── pacing_controller.py # Adaptive camera zoom & transition gates
│   ├── prompt_assembler.py  # Builds per-turn context from rules + lore + state
│   ├── state_parser.py      # Parses XP / currency / SYS receipts
│   ├── style_contract.py    # Style contract validator & prose linter
│   ├── transaction_manager.py # Two-phase commit & idempotency manager
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
├── campaign_config.json   # Theme, metrics, operational mode, style contract, HUD definition
├── CONFIG.yaml            # Model / temperature / context budgets
├── GAMEPLAY/              # status, items, relations (JSON + Markdown)
├── IDEAS/                 # narrative_steering.md — long-term arcs
├── WORLD_BIBLE/           # CORE, PLACES, PEOPLE, FACTIONS, GUIDES
├── WORLD_FOUNDATION/      # world_foundation.json — facts, factions, rumors, mysteries
└── TURNS/                 # ACTIVE/ (rolling window) + ARCHIVE/ (full history)
```

---

## Evolution Architecture

The Whimsy evolution architecture coordinates five modular subsystems into a single end-to-end orchestrated pipeline:

### 1. Operational Modes (`ENGINE/mode_validator.py`)
- **`classic_cyoa`**: Strict option selection mode. Deterministically validates action input against offered choices extracted from the active turn file or upcoming hooks. Rejects arbitrary freeform prose and compound/chained actions (e.g. `1 and then search`) with HTTP 400 without mutating campaign state or creating turn files.
- **`freeform_simulation`**: Emergent sandbox simulation mode. Accepts arbitrary prose and compound actions, allowing emergent player intent while enforcing downstream consequence arithmetic.

### 2. Adaptive Narrative Focus Controller (`ENGINE/pacing_controller.py`)
- **Camera Zoom Levels**: Evaluates player intent to dynamically assign narrative focus: `detailed_scene` (conversations, combat, discoveries), `short_summary` (routine transit, chores), `montage` (multi-day training, prolonged voyages), or `time_skip` (explicit narrative jumps).
- **Narrative Intensity Guard**: Recommends appropriate intensity (1–5) and strictly keeps ordinary scenes at intensity 1–2, preventing unearned artificial drama escalation.
- **Transition Validation Gates**: Enforces anti-degradation rules that block instantaneous location jumps and unapproved time skips when `unresolved_intentions` exist, unless explicit permission or causal justification is provided.
- **In-Game Time Arithmetic & Event Clocks**: Computes elapsed diegetic time (`advance_time()`), advances diegetic clock/calendar timestamps, and fires scheduled world event clocks as time thresholds are crossed.

### 3. Transactional State Committer (`ENGINE/transaction_manager.py`)
- **Two-Phase Commit**: Stages mutations across `status.json`, `status.md`, `items.json`, `items.md`, `relations.md`, and turn logs before committing atomically with rollback on validation error.
- **Deterministic Idempotency**: Turn transaction IDs are generated as `<turn_number>_<action_hash_12>`, recorded in `.transaction_log.json`. Duplicate requests and network retries return committed state without applying duplicate resource or relationship deductions.
- **Narration-State Decoupling**: GM prose generation is strictly decoupled from state mutation, ensuring arithmetic integrity.

### 4. Persistent Style Contract (`ENGINE/style_contract.py`)
- **Prose Linter**: Validates generated narrative against campaign style contracts to prevent narrative degradation across long campaigns.
- **Prohibited Patterns**: Automatically flags and bans modern STEM/calculus jargon (e.g. *reynolds quotients*, *shunt tolerances*), decorative micro-SFX in mundane scenes (*sparks danced on your fork*), narrator praise/editorializing (*with breathtaking prowess*), and formulaic turn closings (*what will you do?*).
- **Readability Bounds**: Enforces maximum sentence length (35 words) and average sentence word limits.

### 5. World-First Initialization (`WORLD_FOUNDATION/world_foundation.json`)
- **Epistemic Separation**: Distinguishes between Immutable Facts (unalterable ground truths), Mutable World State (epoch, territory, resource distribution), Independent Factions (autonomous objectives and simmering tensions), and NPC Knowledge Maps (verified known truths, ignorance boundaries, and misconceptions).
- **Canon Secrets & Mysteries**: Unresolved mysteries remain strictly flagged with `[HIDDEN FROM PROTAGONIST VIEW - CANON SECRET]` until justified in-world discovery conditions are satisfied.
- **Pure Sandbox Gameplay**: Enables campaigns to initiate and evolve without pre-scripted plots or railroading.

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
| `GET`  | `/health`  | Status + active diagnostics (mode, zoom, elapsed time, features) |
| `POST` | `/generate`| Orchestrated 7-step turn generation pipeline         |

### Run the PWA

```bash
python3 -m http.server 3000 --directory UI
# open http://localhost:3000
```

### Run the tests

```bash
bash tests/run_all_tests.sh
# or run suites individually:
python3 -m unittest discover -s tests
node --test tests/*.js
```

---

## Creating a campaign

1. Copy `CAMPAIGNS/template_campaign/` to `CAMPAIGNS/<your_campaign_id>/`.
2. Fill in `campaign_config.json` (set `operational_mode`, `style_contract`, `metrics`, and theme).
3. Populate `WORLD_FOUNDATION/world_foundation.json`, `WORLD_BIBLE/`, and `GAMEPLAY/`.
4. Start the engine and UI; the prompt assembler and engine pipeline handle orchestration.

See `GLOBAL/CAMPAIGN_INIT_SPEC.md` for the full contract.

---

## Documentation

- `INDEX.md` — architecture and directory reference
- `GLOBAL/` — the authoritative rules every turn must follow
- `openspec/specs/` — formal specs for the persistence contract, campaign schema, UI renderer, and local engine
- `AGENTS.md` — the GM/agent operating protocol

---

## License

Released under the [MIT License](LICENSE).
