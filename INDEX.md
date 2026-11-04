# Project Whimsy / CYOA Engine — Documentation Index

## Metadata

    Document ID:      INDEX
    Title:            CYOA Engine Architecture & Documentation Index
    Category:         Index
    Status:           Active
    Current Focus:    End-to-End Evolution Architecture, Pacing & Transactional State Commits

---

## Directory Hierarchy & Single Source of Truth

```
Whimsy/
├── GLOBAL/                                 # Authoritative Global Engine Rules (Single Source of Truth)
│   ├── CORE-001_HARD_CONSTRAINTS.md        # DOC 1: Absolute constraints, priority hierarchy, arithmetic integrity
│   ├── CORE-002_TURN_ARCHITECTURE.md       # DOC 2: Turn execution loop, action points, routines, status screen schema
│   ├── CORE-003_ANTI_DEGRADATION.md        # DOC 3: Prose standards, anti-bloat guards, GM momentum
│   ├── CAMPAIGN_CONTRACT.md                 # Mandatory truth, consequences, clocks & knowledge contract
│   ├── CAMPAIGN_INIT_SPEC.md               # Campaign scaffolding and initialization specifications
│   └── SCHEMAS/                            # Formal JSON schemas for engine & UI generation
│       ├── campaign_init.schema.json       # Specification for campaign themes, metrics, and HUD sections
│       └── turn_state.schema.json          # Specification for living machine state (status.json)
│
├── CAMPAIGNS/                              # Air-Gapped Campaign Universes
│   └── <campaign_id>/                      # e.g., template_campaign
│       ├── campaign_config.json            # Theme, metrics, operational mode, style contract, HUD definition
│       ├── CONFIG.yaml                     # Campaign settings (model, temperature, context budgets)
│       ├── GAMEPLAY/                       # Dedicated Living Gameplay Records (Dual Markdown + JSON)
│       │   ├── status.json                 # Living machine state for UI hydration & zero-drift mutation
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
│       ├── WORLD_FOUNDATION/               # World-First Ground Truths & Epistemic Separation
│       │   └── world_foundation.json       # Immutable facts, mutable world state, factions, secrets
│       └── TURNS/                          # Turn-by-Turn Granular Preservation
│           ├── ACTIVE/                     # Rolling active window (individual turn_XXXX.md files)
│           └── ARCHIVE/                    # Auto-migrated turns (>15) & long transcripts
│
├── ENGINE/                                 # Core Engine Implementation
│   ├── engine.py                           # Standalone orchestrator server (/generate, /health)
│   ├── mode_validator.py                   # Deterministic mode validation (classic_cyoa vs freeform_simulation)
│   ├── pacing_controller.py                # Adaptive narrative focus, zoom levels, intensity & event clocks
│   ├── prompt_assembler.py                 # Assembles: GLOBAL + WORLD_FOUNDATION + WORLD_BIBLE + GAMEPLAY + turns
│   ├── state_parser.py                     # Extracts narrative, numbered choices, and arithmetic deltas
│   ├── style_contract.py                   # Persistent language & style contract linter
│   ├── transaction_manager.py              # Two-phase atomic state committer & idempotency manager
│   └── turn_archiver.py                    # Automatically rolls turn N-15 into ARCHIVE/
│
├── UI/                                     # Installable PWA Frontend
│   ├── index.html                          # Semantic viewport and HUD layout
│   ├── app.js                              # Client logic, local filesystem sync & Evolution HUD updates
│   ├── styles.css                          # High-contrast accessible theme and responsive rules
│   └── gameplay_manifest.json              # Bundled fallback data for offline template sandbox
│
└── INDEX.md                                # This navigation index
```

---

## Architectural Rules & Evolution Subsystems

1. **Strict Air-Gap**: No campaign may reference files, states, or lore from another campaign directory.
2. **Deterministic Operational Modes**:
   - `classic_cyoa`: Strict option selection mode. Action input is validated against offered choices extracted from the active turn file. Compound and freeform inputs are rejected with HTTP 400 without state mutation or turn file generation.
   - `freeform_simulation`: Emergent sandbox simulation mode. Prose and compound actions are accepted, preserving full player agency while driving downstream simulation rules.
3. **Adaptive Narrative Focus & Camera Zoom**:
   - The focus controller assigns narrative camera zoom (`detailed_scene`, `short_summary`, `montage`, `time_skip`) based on player intent and activity.
   - Routine training and transit default to summary or montage; combat and decisions default to detailed scene.
   - Ordinary scenes strictly maintain intensity 1–2, preventing unearned artificial escalation.
   - Transition validation gates block unauthorized time skips and unearned location jumps when `unresolved_intentions` exist.
   - In-game diegetic time arithmetic (`advance_time()`) updates timeline stamps and fires scheduled world event clocks.
4. **Two-Phase Atomic State Commits & Idempotency**:
   - Narrative generation is decoupled from state mutation.
   - Mutations across `status.json`, `status.md`, `items.json`, `items.md`, and turn logs are staged in memory and committed atomically.
   - Deterministic transaction IDs (`<turn_number>_<action_hash_12>`) are stored in `.transaction_log.json`. Retried requests return committed state without duplicate resource or relationship changes.
5. **Persistent Language & Style Contract**:
   - Automated style linter evaluates generated turns against campaign style contracts.
   - Prohibits modern STEM/calculus jargon, decorative micro-SFX in mundane scenes, narrator praise/editorializing, and formulaic turn closings.
   - Enforces sentence length limits (max 35 words/sentence).
6. **World-First Epistemic Separation**:
   - `WORLD_FOUNDATION/world_foundation.json` provides ground truths prior to narrative generation.
   - Epistemic categories: Immutable Facts, Mutable World State, Factions & Tensions, NPC Knowledge Boundaries, Rumors & Beliefs, and Canon Secrets.
   - Canon secrets are strictly flagged `[HIDDEN FROM PROTAGONIST VIEW - CANON SECRET]` until justified in-world discovery conditions are met.
7. **Per-Turn Preservation & Rolling Context**:
   - Every turn is recorded in `TURNS/ACTIVE/turn_XXXX.md`.
   - The active window maintains the latest 15 turns for prompt context; older turns automatically roll into `TURNS/ARCHIVE/`.
