## Context

Whimsy is a local-first, highly extensible Choose-Your-Own-Adventure (CYOA) engine. In prolonged text-based RPGs, two fatal failure modes commonly occur:
1. **State Desynchronization & Math Hallucinations**: Standard LLMs cannot reliably increment inventory, tracking currencies (such as `3G 6S 20C`), or calculate XP deltas purely through narrative text.
2. **Context Window Exhaustion & Narrative Drift**: As turn count expands (e.g. Turn 245+), injecting raw past turns causes context degradation and prompt budget exhaustion.

Whimsy solves this by establishing:
- A dual persistence model separating machine state (JSON) from narrative context (Markdown).
- A genre-agnostic campaign schema that drives both backend state validation and frontend UI component generation.
- A rolling active turns window (maximum 15 turns) managed by an automated turn archiver.
- A local Antigravity server bridging local browser PWA interactions with deterministic game loop mutations.

## Goals / Non-Goals

**Goals:**
- Provide deterministic arithmetic guarantees for XP, currency, strain, and checkpoint tokens.
- Support arbitrary campaign genres (e.g. scholastic fantasy, cosmic pantheon, cyber-spiritual sci-fi) through unified schema contracts.
- Render dynamic top bar metrics and HUD components directly from JSON schema and state without hardcoded frontend templates.
- Maintain seamless offline and local-first execution via local Python HTTP engine and service worker caching.
- Enforce strict air-gapping between independent campaign universes.

**Non-Goals:**
- Centralized multi-tenant database persistence: The architecture relies on the local file system (File System Access API or local disk files).
- Real-time multiplayer synchronization: The engine is designed for single-player narrative depth.
- Replacing creative LLM storytelling: The engine enforces rules, bounds, and receipts, while the LLM generates narrative prose.

## Decisions

### 1. Dual Persistence Architecture: Machine JSON + Narrative Markdown
- **Decision**: Every campaign's `GAMEPLAY/` directory maintains parallel files: `status.json` and `status.md`, `relations.json` and `relations.md`, `items.json` and `items.md`.
- **Rationale**: LLMs reason best over structured Markdown prose, while UI hydration, metric calculations, and automated delta parsers require deterministic JSON data types.
- **Alternatives Considered**: 
  - Pure JSON: Makes GM prompt injection verbose and strips human/LLM readability.
  - Pure Markdown: Causes fragile regex parsing and arithmetic drift over hundreds of turns.

### 2. Schema-Driven Dynamic UI Engine
- **Decision**: Define campaign UI layouts, themes, top bar metric paths, and status accordion tabs in `campaign_config.json`, conforming to `GLOBAL/SCHEMAS/campaign_init.schema.json`.
- **Rationale**: Allows adding new campaigns with completely unique visual aesthetics and custom vitals (e.g., Divinity/Faith in a cosmic campaign vs Energy/Stress in a grounded campaign) without writing a single line of new CSS or JS.
- **Alternatives Considered**: Hardcoding campaign views in HTML templates, which violates the genre-agnostic principle.

### 3. Delimited Turn Resolution Receipts
- **Decision**: Engine output mandates strict machine-parsable blocks: `[XP RESOLUTION: ...]`, `[CURRENCY RESOLUTION: ...]`, and `[SYS: ...]`.
- **Rationale**: Allows `StateParser` (Python) and `updateAndPersistState` (JavaScript) to extract exact state deltas, update both JSON and Markdown, and guarantee zero drift.
- **Alternatives Considered**: Asking the LLM to output full replacement state JSON directly, which degrades narrative writing quality and increases token consumption.

### 4. Rolling Turn Window with Lossless Archival
- **Decision**: Active prompt context loads only the most recent 15 turns (`TURNS/ACTIVE/`). Turns older than 15 automatically migrate to `TURNS/ARCHIVE/`.
- **Rationale**: Preserves 100% loss-less game history on disk while bounding prompt context size to avoid context exhaustion and token degradation.

## Risks / Trade-offs

- **[Risk] State Parser Regex Mismatch**: If LLM deviates from receipt syntax, automated mutation might fail.
  - **Mitigation**: Robust multi-tier regex matching with fallback regexes in both Python and JavaScript engines.
- **[Risk] Browser Sandbox Storage Constraints**: Browser File System Access API requires user permission prompts.
  - **Mitigation**: Fallback to bundled JSON data files and offline Service Worker cache when no directory handle is active.
