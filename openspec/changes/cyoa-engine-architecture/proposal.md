## Why

The Whimsy CYOA project is a choice-driven, modular RPG orchestration platform designed for extreme narrative fidelity, arithmetic consistency, and zero state drift across long campaigns. As campaigns scale past hundreds of turns, LLM hallucinations, prose bloat, and state mutations frequently cause unrecoverable narrative desynchronization.

This change formalizes the complete architecture of Whimsy under the OpenSpec standard. It establishes rigid specifications for dual-state persistence, genre-neutral JSON schemas, client-side dynamic UI rendering, and the local Antigravity orchestration engine.

## What Changes

- **Dual Persistence Contract**: Formalizes synchronization between machine-readable JSON states (`status.json`, `relations.json`, `items.json`) and human/LLM-readable Markdown representations (`status.md`, `relations.md`, `items.md`).
- **Genre-Agnostic Campaign Schema**: Establishes schema specifications for campaign initialization (`GLOBAL/SCHEMAS/campaign_init.schema.json`) and dynamic turn state validation (`GLOBAL/SCHEMAS/turn_state.schema.json`).
- **Client UI Rendering Engine**: Specifies the progressive web application (PWA) client interface, covering dynamic top bar metric synchronization, adaptive HUD cards vs Living Record markdown views, responsive mobile drawer, and offline-resilient network-first service worker caching (`sw.js`).
- **Local Antigravity Engine**: Specifies the standalone Python HTTP orchestration server (`ENGINE/engine.py`), including CORS headers, local simulation with deterministic receipt resolution (`[XP RESOLUTION]`, `[CURRENCY RESOLUTION]`, `[SYS]`), and fallback numbered choice generation.

## Capabilities

### New Capabilities
- `dual-persistence-contract`: Machine JSON and human/LLM Markdown dual persistence contract guaranteeing deterministic state hydration, zero-drift mutations, and rich narrative context injection.
- `genre-agnostic-campaign-schema`: Thematic, architectural, and living state JSON schemas enabling air-gapped campaign definitions across arbitrary genres (fantasy, sci-fi, cosmic pantheon, etc.).
- `client-ui-rendering-engine`: PWA client interface engine featuring top-bar metric synchronization, dynamic HUD cards vs living markdown toggles, responsive drawer navigation, and network-first service worker caching.
- `local-antigravity-engine`: Standalone local Python HTTP server providing CORS-enabled orchestration, deterministic receipt calculations, turn state mutation, and numbered choice fallbacks.

### Modified Capabilities
<!-- None: This is the initial architectural specification suite. -->

## Impact

- **Affected Systems**: `GLOBAL/SCHEMAS/`, `ENGINE/` (`engine.py`, `prompt_assembler.py`, `state_parser.py`, `turn_archiver.py`), `UI/` (`app.js`, `index.html`, `styles.css`, `sw.js`), and `CAMPAIGNS/` active state files.
- **Dependencies**: No external runtime dependencies; engine utilizes Python 3 standard library and client runs on vanilla JavaScript with Service Worker API.
- **Backwards Compatibility**: Fully backwards compatible with existing campaign saves and active turn files.
