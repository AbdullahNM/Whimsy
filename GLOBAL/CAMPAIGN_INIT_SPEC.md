# CYOA Engine — Genre-Agnostic Campaign Initialization Specification

## 1. Architectural Philosophy

The CYOA story engine is completely **genre-agnostic**. The core runtime does not hardcode fantasy classes, hit points, or specific narrative rules into its presentation logic. Whether a story is a **High Fantasy Academy**, a **Cosmic Pantheon Simulator**, a **Teen Romance**, a **Cyberpunk Heist**, a **Post-Apocalyptic Survival**, or a **1940s Noir Murder Mystery**, the engine treats them all through a unified contract. The governing gameplay contract is [`CAMPAIGN_CONTRACT.md`](CAMPAIGN_CONTRACT.md): every meaningful choice must create a persistent consequence, and public state may never disclose GM-private facts.

```
┌────────────────────────────────────────────────────────────────────────┐
│                      CAMPAIGN INITIALIZATION SPEC                      │
├────────────────────────────────┬───────────────────────────────────────┤
│ 1. campaign_config.json        │ Theme, Metrics, Badge, Tabs, Sections │
│ 2. GAMEPLAY/status.json        │ Deterministic Living Machine State    │
│ 3. GAMEPLAY/relations.json     │ Social Web / Suspects / Factions      │
│ 4. GAMEPLAY/items.json         │ Assets, Gear, Clues, Currency         │
│ 5. TURNS/ACTIVE/turn_0001.md   │ Living Scene Narrative & First Prompt │
│ 6. clocks + public_state        │ Stakes, pressures, known consequences │
└────────────────────────────────┴───────────────────────────────────────┘
```

The Progressive Web App (PWA) client reads this contract and **dynamically constructs its entire UI**:
- Color variables, fonts, and glowing accents
- Top-bar floating metric pills
- Protagonist / Entity header badge
- Live percentage progression bars
- Numeric counters and asset boxes
- Mastery / Aptitude / Standing spectra
- Inventory / Clue / Keepsake checklists
- Tab navigation and living markdown archives

---

## 2. The Campaign Initialization Contract

Every campaign directory under `CAMPAIGNS/<campaign_id>/` must provide the following standard structure:

```
CAMPAIGNS/<campaign_id>/
├── campaign_config.json            # Authoritative UI & theme specification
├── CONFIG.yaml                     # Engine parameters (model, temperature, turn window)
├── GAMEPLAY/
│   ├── status.json                 # Machine vitals matching campaign_config.json paths
│   ├── status.md                   # Human-readable Markdown record
│   ├── relations.json              # Social web, factions, peers, or suspects
│   ├── relations.md                # Human-readable Markdown social record
│   ├── items.json                  # Currency, equipment, clues, or keepsakes
│   ├── items.md                    # Human-readable Markdown inventory record
│   └── upcoming_hooks.md           # Immediate next-turn seeds & transitional options
├── IDEAS/
│   └── narrative_steering.md       # GM-private conditional pressures, secrets, and branch triggers
├── WORLD_BIBLE/                    # Domain-separated lore modules
│   ├── CORE/                       # Fundamental world rules & physics
│   ├── PLACES/                     # Key locations & environments
│   ├── PEOPLE/                     # Major character dossiers
│   └── FACTIONS/                   # Organizations, institutions, or cliques
└── TURNS/
    ├── ACTIVE/                     # Rolling window of recent turns (turn_0001.md, etc.)
    └── ARCHIVE/                    # Permanent history archives
```

`GAMEPLAY/` is public state: it may only contain established facts and clearly-marked suspicions. Secrets, unrevealed traits, hidden clocks, and authorial plans belong in `IDEAS/`; they must never be copied into a player dossier or status panel.

## 2.1 Consequence and Clock Requirements

Every new campaign begins with one visible scene clock and one visible or suspected arc clock in `status.json`. Each meaningful turn must update a resource, clock, relationship, public flag, available hook, scene, or time. Routine moments should be grouped into macro turns rather than padded into separate choices.

Roadmaps are conditional pressure maps. They may describe what an NPC or faction will do if ignored, but never prescribe the player's eventual decision, success, romance, or discovery.

---

## 3. Configuration Schema Reference (`campaign_config.json`)

Validated against [`GLOBAL/SCHEMAS/campaign_init.schema.json`](GLOBAL/SCHEMAS/campaign_init.schema.json):

### A. `theme`
```json
"theme": {
  "bg_dark": "#0a0b10",         // Main app canvas
  "bg_slate": "#12141e",        // Sidebar and containers
  "bg_card": "#181b29",         // Stat and scene cards
  "gold_primary": "#00f0ff",    // Primary accent color
  "gold_dim": "#0099aa",        // Secondary accent color
  "accent_glow": "rgba(0, 240, 255, 0.18)", // Card and header glow
  "text_ivory": "#e6f8ff",      // High-contrast prose text
  "font_family": "system-ui, sans-serif"    // Typography stack
}
```

### B. `metrics` (Top-Bar Floating Pills)
Array of metric definitions displayed in the top bar:
* `id`: Unique identifier (e.g., `turn`, `xp`, `humanity`, `stress`, `clues`)
* `label`: Display label on pill
* `type`: `"counter"`, `"progress"`, `"currency"`, or `"text"`
* `path`: Dot-notation path to current value in `status.json` (e.g. `progression.xp`)
* `max_path`: Optional dot-notation path to maximum limit (e.g. `progression.xp_threshold`)
* `color`: Optional accent color override
* `regex`: Fallback regex for markdown-only parsing

### C. `entity_header` (Protagonist / Player Card)
* `title_path`: Path to character name / callsign
* `subtitle_path`: Path to archetype, division, or role
* `tag_paths`: Array of paths to badge tags (e.g. year, tier, background, moral alignment)

### D. `status_sections` (HUD Accordions)
* `progression_bars`: Array of bars with `label`, `path`, `max_path`, `color`, and `unit`.
* `stat_grid`: Array of boxes with `label`, `path`, and `suffix`.
* `attributes_grid`: Dictionary path (`dict_path`) and `max_scale` (e.g. 100).
* `inventory_status`: Array path (`array_path`) for key checklist items.
* `scene_anchor`: Coordinates mapping `location_path`, `context_path`, and `time_path`.

---

## 4. Multi-Genre Reference Implementation Examples

### Example 1: Teen Romance / Slice of Life (`summer_hearts`)
* **Theme**: Soft pastel rose, warm slate, elegant serif/sans mix.
* **Top Metrics**: Day (`timeline.day`), Chemistry (`vitals.chemistry_pct`), Drama (`vitals.drama_level`), Allowance (`wallet.display`).
* **Protagonist**: Maya Lin | Year 11 Transfer Student | Tags: "Art Club", "Shy Debater", "Scholarship".
* **Progression Bars**:
  * *Romantic Chemistry* (72 / 100)
  * *Academic Stress* (28 / 100)
* **Stat Grid**: Allowance ($45.50), Unread Texts (3), Reputation (Friendly).
* **Attributes**: Empathy (35), Witty Banter (28), Academics (34), Artistry (40).
* **Relations**: Crushes (Leo, Julian), Best Friends (Chloe), Rivals (Amber).
* **Inventory**: Sketchbook, Lucky Coin, Vintage Walkman, Secret Letter.

### Example 2: Cyberpunk / Espionage (`neon_syndicate`)
* **Theme**: Deep obsidian, hot neon magenta (`#ff007f`), cyan borders.
* **Top Metrics**: Cycle (`turn`), Humanity (`cyberware.humanity_remaining`), Heat (`factions.police_heat`), Creds (`wallet.credits`).
* **Protagonist**: 'Cipher' (Jax Rivera) | Solo Infiltrator | Tags: "Ex-Corporate", "Reflex Boosted", "Tier 2 Fixer".
* **Progression Bars**:
  * *Humanity Buffer* (45 / 100)
  * *Nanite Overclock* (12 / 50)
* **Stat Grid**: Black Market Creds (4,250 ₡), Burner Comms (2), Safehouse Status (Secure).
* **Attributes**: Neural Hacking (32), Ballistic Accuracy (30), Streetwise (28), Subterfuge (25).
* **Relations**: Fixers (Mr. Sato), Tech Docs (Doc V), Corporate Rivals (Arasaka Taskforce).
* **Inventory**: Monomolecular Blade, Cyberdeck Militech v4, Encrypted Datashards.

### Example 3: 1940s Noir Murder Mystery (`cold_case_1947`)
* **Theme**: Sepia newsprint dark slate, muted amber, typewriter monospace.
* **Top Metrics**: Hour (`case.hours_remaining`), Suspicion (`vitals.police_suspicion`), Clues (`case.clues_found`), Scotch (`vitals.stamina`).
* **Protagonist**: Detective Ray Holt | Private Eye | Tags: "WWII Veteran", "Disgraced Detective", "Raincoat & Fedora".
* **Progression Bars**:
  * *Investigation Timeline* (18 / 48 Hours)
  * *Police Suspicion* (15 / 100)
* **Stat Grid**: Retainer Fee ($120), Verified Alibis (3 / 6), Lead Clues (7).
* **Attributes**: Forensic Deduction (35), Interrogation (30), Street Forensics (28), Brawl (22).
* **Relations**: Suspects (The Widow Sterling, The Chauffeur), Informants (Louie Two-Times), Police Liaison (Inspector Hayes).
* **Inventory**: .38 Snub Revolver, Magnifying Loupe, Bloodstained Matchbook, Safe Deposit Key.

### Example 4: Dystopian Survival (`ashen_frontier`)
* **Theme**: Ash grey, toxic moss green (`#10b981`), hazard yellow.
* **Top Metrics**: Day (`day`), Radiation (`vitals.rad_dose`), Hunger (`vitals.calorie_deficit`), Scrap (`purse.scrap`).
* **Protagonist**: Karr | Wasteland Scavenger | Tags: "Immune Carrier", "Old World Engineer", "Solitary".
* **Progression Bars**:
  * *Radiation Resistance* (85 / 100)
  * *Hydration Buffer* (40 / 100)
* **Stat Grid**: Standard Rounds (18), Purified Water (3 Phials), Scrap Metal (140).
* **Attributes**: Field Medicine (26), Scavenging (34), Ballistics (28), Mechanics (32).

---

## 5. Automated Scaffolding & Verification Workflow

When initializing a new campaign:
1. Copy [`CAMPAIGNS/template_campaign/`](CAMPAIGNS/) into `CAMPAIGNS/<new_id>/`.
2. Fill out `campaign_config.json` with the genre palette, metrics, and sections.
3. Populate `GAMEPLAY/status.json` with matching initial vitals.
4. Populate `GAMEPLAY/relations.json` and `GAMEPLAY/items.json`.
5. Write `TURNS/ACTIVE/turn_0001.md` containing the hook scene and choices.
6. Refresh the client: the campaign dropdown will automatically detect and render the universe.
