# Project Whimsy / CYOA Engine — Documentation Index

## Metadata

    Document ID:      INDEX
    Title:            CYOA Engine Architecture & Documentation Index
    Category:         Index
    Status:           Active
    Current Focus:    Modular Engine, Single Source of Truth, Turn Archiving

---

## Directory Hierarchy & Single Source of Truth

```
Whimsy/
├── GLOBAL/                                 # Authoritative Global Engine Rules (Single Source of Truth)
│   ├── CORE-001_HARD_CONSTRAINTS.md        # DOC 1: Absolute constraints, priority hierarchy, arithmetic integrity
│   ├── CORE-002_TURN_ARCHITECTURE.md       # DOC 2: Turn execution loop, action points, routines, status screen schema
│   ├── CORE-003_ANTI_DEGRADATION.md        # DOC 3: Prose standards, anti-bloat guards, GM momentum
│   ├── CAMPAIGN_CONTRACT.md                 # Mandatory truth, consequences, clocks & knowledge contract
│   └── SCHEMAS/                            # Formal JSON schemas for engine & UI generation
│       ├── campaign_init.schema.json       # Specification for campaign themes, metrics, and HUD sections
│       └── turn_state.schema.json          # Specification for living machine state (status.json)
│
├── CAMPAIGNS/                              # Air-Gapped Campaign Universes
│   └── <campaign_id>/                      # e.g., template_campaign
│       ├── campaign_config.json            # Self-contained schema encoding (theme, metrics, HUD sections)
│       ├── CONFIG.yaml                     # Campaign settings (model, temperature, context budgets)
│       ├── GAMEPLAY/                       # Dedicated Living Gameplay Records (Dual Markdown + JSON)
│       │   ├── status.json                 # Deterministic machine state for UI hydration & zero-drift mutation
│       │   ├── status.md                   # Human-readable Markdown record for narrative & LLM context
│       │   ├── relations.md                # Social standing, peers, faculty, factions
│       │   ├── items.md                    # Active inventory, purse, catalysts, keys & passes
│       │   └── upcoming_hooks.md           # Immediate next-turn seeds & transitional options
│       ├── IDEAS/                          # Story Steering & Narrative Concept Banks
│       │   └── narrative_steering.md       # Long-term arcs, latent talent triggers, faction plots
│       ├── WORLD_BIBLE/                    # Domain-Separated Modular Lore
│       │   ├── CORE/                       # Magic mechanics, tier progression, economy, visual standards
│       │   ├── PLACES/                     # Cities, districts, buildings, and travel routes
│       │   ├── PEOPLE/                     # Individual character profiles and rosters
│       │   ├── FACTIONS/                   # Organisations, rivalries, and power blocs
│       │   └── GUIDES/                     # Turn execution guide, status screen schema guide
│       └── TURNS/                          # Turn-by-Turn Granular Preservation
│           ├── ACTIVE/                     # Rolling active window (individual turn_XXXX.md files)
│           └── ARCHIVE/                    # Auto-migrated turns (>15) & long transcripts
│
├── ENGINE/                                 # Core Engine Implementation
│   ├── engine.py                           # Main orchestrator
│   ├── prompt_assembler.py                 # Assembles: GLOBAL + WORLD_BIBLE + STATE + last <=15 ACTIVE turns
│   ├── turn_archiver.py                    # Automatically rolls turn N-15 into ARCHIVE/
│   └── state_parser.py                     # Extracts narrative, numbered choices, and arithmetic deltas
│
└── INDEX.md                                # This navigation index
```

---

## Architectural Rules

1. **Strict Air-Gap**: No campaign may reference files, states, or lore from another campaign directory.
2. **Per-Turn Preservation**:
   - Every single turn is preserved verbatim in its own timestamped file (`turn_XXX.md`).
   - The engine maintains only the latest **15 turns** in `TURNS/ACTIVE/` for LLM context injection.
   - Older turns automatically migrate into `TURNS/ARCHIVE/` to prevent context explosion while guaranteeing 100% loss-less history.
3. **Modular World Building**:
   - Instead of a single giant lore file, `WORLD_BIBLE/` is split into distinct categories (`geography.md`, `history.md`, `magic.md`, `factions.md`, `mechanics.md`).
   - The prompt assembler injects relevant categories dynamically based on the current scene.
4. **Proactive State Arithmetic**:
   - Stat and inventory changes must have explicit causal roots in the narrative.
   - State is updated deterministically in `GAMEPLAY/` (`status.md`, `items.md`, `relations.md`).
5. **Consequence-Driven Choices**:
   - Every meaningful action records a cost, outcome, and persistent change.
   - `GAMEPLAY/status.json` is the only live machine authority; legacy `STATE/` material is archival.
   - Public state may contain only known or clearly suspected facts. GM-private material stays out of player-facing records.
