# Dual Persistence Contract

## Purpose
Guarantees deterministic synchronization between machine-readable JSON states (`status.json`, `relations.json`, `items.json`) and human/LLM-readable Markdown representations (`status.md`, `relations.md`, `items.md`), eliminating state drift and arithmetic hallucinations across extended campaign turns.

## Requirements

### Requirement: Dual Persistence File Symmetry
The CYOA engine SHALL maintain parallel machine-readable JSON files and human/LLM-readable Markdown files in each campaign's `GAMEPLAY/` directory. Specifically, `status.json` must correspond to `status.md`, `relations.json` to `relations.md`, and `items.json` to `items.md`.

#### Scenario: Verify dual persistence structure
- **WHEN** a campaign `GAMEPLAY/` directory is inspected
- **THEN** both JSON (`status.json`, `relations.json`, `items.json`) and Markdown (`status.md`, `relations.md`, `items.md`) files exist and reflect consistent state.

### Requirement: Deterministic Mutation from Resolution Receipts
The state parser SHALL parse delimited GM resolution blocks (`[XP RESOLUTION: ...]`, `[CURRENCY RESOLUTION: ...]`, `[SYS: ...]`) and apply deterministic state mutations to both machine JSON and human Markdown representations without arithmetic drift.

#### Scenario: XP delta resolution
- **WHEN** GM output contains `[XP RESOLUTION: Previous: 315 | Delta: +15 (Sparring) | New Total: 330 / 500]`
- **THEN** the state mutation updates `progression.xp` to 330 in `status.json` and updates `XP: 330 / 500` in `status.md`.

#### Scenario: Currency delta resolution
- **WHEN** GM output contains `[CURRENCY RESOLUTION: Previous: 3G 6S 20C | Delta: +5S | New Purse: 3G 11S 20C]`
- **THEN** the state mutation updates `purse.display` and denomination counters in `status.json` and updates the coin entry in `items.md`.

### Requirement: Scene Anchor and Timeline Synchronization
Every state update SHALL record the current `turn`, `timeline`, and `scene_anchor` (comprising location, context, and narrative time) in `status.json` and reflect current position in `status.md`.

#### Scenario: Scene anchor preservation across turns
- **WHEN** a new turn executes and GM output indicates the protagonist moves to a new location
- **THEN** `scene_anchor.location`, `scene_anchor.context`, and `scene_anchor.time` are persisted in `status.json`.
