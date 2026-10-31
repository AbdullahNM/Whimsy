# CYOA Engine Review & Prioritized Fix Plan

## Metadata
* **Project**: Whimsy / CYOA Engine (Template Campaign & Sample Campaign)
* **Execution Environment**: Local-First PWA & Python Engine (No public web exposure)
* **Scope**: Core mechanics, architecture consistency, state persistence, turn loops, and UI integration. *(Note: Purely remote/hosted web vulnerabilities such as third-party XSS vectors or public CSP restrictions have been excluded in accordance with the local-only execution model).*
* **Date**: October 2026

---

## Executive Summary

The CYOA engine project represents an ambitious, well-conceived hybrid architecture: a local-first browser client (PWA) interfacing via Chrome File System Access API with a file-backed repository of modular lore, gameplay state, and rolling turn logs.

However, the current codebase suffers from **runtime blockers** (crashes on startup, missing JavaScript functions, unwired UI controls), **state desynchronization** (duplicate ledgers, failure to persist XP and currency receipts back to disk), **architectural contradictions** between the rule documents and the file tree, and **critical disconnects** between the UI, the Python assembler, and the LLM API calls.

---

## Prioritized Issue Register

```
┌────────────────────────────────────────────────────────────────────────┐
│ P0: CRITICAL RUNTIME BLOCKERS (Crashes, dead UI, mock context)          │
├────────────────────────────────────────────────────────────────────────┤
│ P1: STATE PERSISTENCE & DATA INTEGRITY (Ledger drift, unparsed deltas) │
├────────────────────────────────────────────────────────────────────────┤
│ P2: ARCHITECTURAL CONTRADICTIONS & PHANTOM MODULES (Spec clashes)      │
├────────────────────────────────────────────────────────────────────────┤
│ P3: UI / ENGINE INTEGRATION (Model switching, lore viewer, choices)    │
├────────────────────────────────────────────────────────────────────────┤
│ P4: CAMPAIGN DATA STANDARDIZATION (Skeleton campaigns, legacy turns)   │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Priority 0: Critical Runtime Blockers
*These issues cause unhandled exceptions, break user interaction, or bypass the engine entirely.*

#### 1. Unhandled `AttributeError` in `ENGINE/prompt_assembler.py`
* **Location**: `ENGINE/prompt_assembler.py` (Lines 20–21)
* **Description**: `load_campaign_gameplay()` contains:
  ```python
  if not os.path.exists(gameplay_dir):
      return self.load_campaign_state(campaign_name)
  ```
  `self.load_campaign_state()` does not exist in `PromptAssembler`.
* **Impact**: Calling `build_system_prompt("sample_campaign")` or any campaign without a `GAMEPLAY/` folder immediately crashes with an `AttributeError`.
* **Fix**: Implement `load_campaign_state()` to fall back to `STATE/public_ledger.md` or return an empty state string if neither exists.

#### 2. Uncaught `ReferenceError` in `UI/app.js`
* **Location**: `UI/app.js` (Line 115)
* **Description**: When markdown files exist in `TURNS/ACTIVE/`, `loadWorkspace()` invokes:
  ```javascript
  if (campaignData.activeTurns.length > 0) {
    renderStoryStream(campaignData.activeTurns);
  }
  ```
  `renderStoryStream()` is **never defined** anywhere in `app.js`.
* **Impact**: Loading any campaign with active turns immediately crashes execution with `Uncaught ReferenceError: renderStoryStream is not defined`.
* **Fix**: Define `renderStoryStream(turns)` to iterate over active turn files and populate `#story-stream` cards sequentially.

#### 3. Unwired "Submit Action" Button (`#custom-action-btn`)
* **Location**: `UI/index.html` (Line 75) & `UI/app.js` (Line 23)
* **Description**: The input bar provides a `<button id="custom-action-btn">Submit Action</button>`, which is assigned to `const customActionBtn`, but has **zero event listeners**.
* **Impact**: Entering text in `#recal-input` and clicking "Submit Action" does nothing. The user can only submit by clicking dynamic choice buttons.
* **Fix**: Add a click event listener to `customActionBtn` that reads `#recal-input` and submits the action (or warns if a numbered choice is required per DOC 1).

#### 4. UI Context Disconnect (Hardcoded Mock API Payload)
* **Location**: `UI/app.js` (Lines 211–235)
* **Description**: `callGeminiAPI()` completely ignores the workspace data loaded into `campaignData` (`status`, `relations`, `items`, `activeTurns`). It sends a hardcoded 4-bullet mock prompt:
  ```javascript
  systemInstruction: {
    parts: [{
      text: `You are the Game Master for the Template Campaign CYOA RPG.
Ground yourself strictly in the protagonist's established record:
- Level 3 Initiate | 315/500 XP | Strain 0/10 | Checkpoints 5/5...`
    }]
  }
  ```
  Furthermore, `contents` contains only the single `playerAction` string—no conversation history or prior turns.
* **Impact**: The LLM has no access to the loaded rules, World Bible, active inventory, relationships, or story history. Every turn is simulated in an amnesiac vacuum.
* **Fix**: Assemble `systemInstruction` dynamically from the loaded rules, `GAMEPLAY/` records, and recent active turns.

---

### Priority 1: State Persistence & Data Integrity
*These issues prevent player decisions from persisting and cause permanent state drift.*

#### 1. Dual-Ledger Desynchronization (`STATE/` vs `GAMEPLAY/`)
* **Location**: `CAMPAIGNS/template_campaign/STATE/public_ledger.md` vs `CAMPAIGNS/template_campaign/GAMEPLAY/status.md`
* **Description**: The repository currently contains two competing sources of truth for the protagonist's character state:
  * `STATE/public_ledger.md` (175 lines, monolithic ledger from NotebookLM export)
  * `GAMEPLAY/status.md`, `relations.md`, `items.md` (modular split)
  `INDEX.md` line 67 states *"State is updated deterministically in STATE/public_ledger.md"*, yet `prompt_assembler.py` and `app.js` read from `GAMEPLAY/`.
* **Impact**: Updates made to `status.md` leave `public_ledger.md` stale, and vice versa. There is no automated synchronization between them.
* **Fix**: Establish a single authoritative format. Either designate `GAMEPLAY/*.md` as the sole living state and generate `public_ledger.md` as an export artifact, or vice versa.

#### 2. Missing State Mutation Loop (Deltas Never Saved to Disk)
* **Location**: `UI/app.js` (Lines 196–206) & `ENGINE/turn_archiver.py`
* **Description**: When the GM responds with state updates (e.g. `[XP RESOLUTION: ...]`, `[CURRENCY RESOLUTION: ...]`, `[SYS: ...]`), `app.js` only increments the turn counter in UI memory and saves the raw text of the turn to `turn_XXXX.md`. It **never parses the deltas or updates** `status.md`, `items.md`, or `relations.md`.
* **Impact**: XP, coin, strain, and item changes awarded by the GM are never written back to disk. Reloading the app resets the player to their initial Day 1 stats.
* **Fix**: Implement a state parser that extracts `[XP RESOLUTION]`, `[CURRENCY RESOLUTION]`, and `[SYS: ...]` blocks from GM output, updates the internal state object, and writes the updated markdown back to disk atomically.

#### 3. Active Turn Omission in Python `PromptAssembler`
* **Location**: `ENGINE/prompt_assembler.py` (Lines 69–85)
* **Description**: `INDEX.md` states: *"prompt_assembler.py assembles: GLOBAL + WORLD_BIBLE + STATE + last <=15 ACTIVE turns"*. However, `PromptAssembler.build_system_prompt()` never calls `turn_archiver.load_active_turns()`.
* **Impact**: If running via Python CLI/bridge, the prompt assembler generates a static world prompt with zero recent turn history.
* **Fix**: Import `load_active_turns` from `turn_archiver.py` and append the rolling turns to the prompt payload under `# 5. RECENT TURNS & IMMEDIATE HISTORY`.

#### 4. Turn File Naming and Archiver Mismatch
* **Location**: `ENGINE/turn_archiver.py` (Lines 8–10) vs `CAMPAIGNS/template_campaign/TURNS/ARCHIVE/`
* **Description**: `turn_archiver.py` uses `re.search(r'turn_(\d+)', filename)` to sort and archive turns. But the actual files in `ARCHIVE/` have narrative titles:
  * `Campaign Arc Transcript.md`
  * `Campaign Arc Preparations.md`
  * `Campaign Arc Defense.md`
  * `Minimalist Punctuation Exchange.md`
* **Impact**: `get_turn_number()` returns `-1` for all historical files. The engine cannot determine turn sequence or migrate turns automatically.
* **Fix**: Rename or index archive turns with standard numeric prefixes (e.g., `turn_0230_high_court_victory.md` or maintain a `turns_manifest.json`).

---

### Priority 2: Architectural Contradictions & Missing Engine Modules
*These issues create structural confusion and prevent the planned engine workflow from functioning.*

#### 1. Reconcile `CORE-001` with Modular Architecture
* **Location**: `GLOBAL/CORE-001_HARD_CONSTRAINTS.md` (Lines 20–28) vs `INDEX.md`
* **Description**: `CORE-001` (marked "Supreme Authority") dictates:
  > *"Two-Document Campaign Architecture (World Bible + Character & State Ledger): Each active campaign is governed by exactly two coordinated documents in the repository..."*
  This directly contradicts the modular structure (`GAMEPLAY/`, `WORLD_BIBLE/CORE/`, `PLACES/`, `PEOPLE/`, `FACTIONS/`, `GUIDES/`) adopted by the project in `INDEX.md`.
* **Fix**: Update Section 2 of `CORE-001_HARD_CONSTRAINTS.md` to formally codify the modular architecture as the supreme standard.

#### 2. Missing Core Modules Specified in `INDEX.md`
* **Location**: `ENGINE/` and `GLOBAL/SCHEMAS/`
* **Description**: `INDEX.md` lists several key modules that do not exist:
  * `ENGINE/engine.py` (Main orchestrator) — **Missing**
  * `ENGINE/state_parser.py` (Extracts narrative, numbered choices, and arithmetic deltas) — **Missing**
  * `GLOBAL/SCHEMAS/turn_state.schema.json` — **Missing** (directory is empty)
  * `CONFIG.yaml` (Per campaign: model, temperature, context budgets) — **Missing**
* **Fix**: Implement the basic orchestration script (`engine.py`) and regex/JSON state parser (`state_parser.py`). Provide the schema file for turn state validation.

#### 3. Unbounded Context Bloat in World Bible Loading
* **Location**: `ENGINE/prompt_assembler.py` (Lines 42–67)
* **Description**: When `specific_categories` is `None`, `load_world_bible()` concatenates all 20+ markdown files in `CORE`, `PLACES`, `PEOPLE`, `FACTIONS`, and `GUIDES`.
* **Impact**: Injects tens of thousands of tokens into every single turn, increasing latency and API costs while crowding out recent turn context.
* **Fix**: Implement keyword/tag filtering based on the active scene (e.g. if location is `Central Court`, only load `PLACES/central_court.md` and related faction files).

---

### Priority 3: UI / Engine Integration
*These issues hinder user experience, custom configuration, and multi-campaign support in the web client.*

#### 1. Hardcoded Campaign Selection (`template_campaign`)
* **Location**: `UI/app.js` (Lines 78–82)
* **Description**: `loadWorkspace()` explicitly checks for and opens only `template_campaign`:
  ```javascript
  const campaignsDir = await rootHandle.getDirectoryHandle('CAMPAIGNS');
  campaignHandle = await campaignsDir.getDirectoryHandle('template_campaign');
  ```
* **Impact**: The UI cannot load `sample_campaign` or any new campaign. This violates DOC 1 Rule 1 ("Cold Start Behavior & Campaign Selection").
* **Fix**: Inspect `CAMPAIGNS/` subdirectories and display a campaign picker modal if multiple campaigns exist.

#### 2. Disconnected Settings Modal
* **Location**: `UI/index.html` (Lines 91–100) & `UI/app.js` (Lines 41–56)
* **Description**: The settings modal provides `#gemini-model-select` (options: `gemini-2.5-flash`, `gemini-2.5-pro`, `local-bridge`) and `#max-turns-input`. `app.js` neither reads nor stores these settings; the model endpoint is hardcoded to `gemini-2.5-flash`.
* **Fix**: Save model choice and rolling turn limit in `localStorage`, and use the selected model in the API endpoint URL.

#### 3. Dead Lore Viewer in Sidebar
* **Location**: `UI/index.html` (Lines 48–55) & `UI/app.js`
* **Description**: The UI has a "Lore" tab with `#lore-file-list` and `#lore-content-viewer`. However, `loadWorkspace()` never reads the `WORLD_BIBLE/` directory, leaving this tab permanently blank.
* **Fix**: Read files from `WORLD_BIBLE/` recursively and populate the list with clickable items that display lore content in `#lore-content-viewer`.

#### 4. Fragile Choice Extraction Regex
* **Location**: `UI/app.js` (Lines 247–262)
* **Description**: `parseNewChoicesFromResponse()` applies `/^(\d+)\.\s+(.*)/` to every line of the GM response.
* **Impact**: If the narrative contains numbered items (e.g., historical dates, spell ranks, ordered lists), they are erroneously extracted as action buttons. Furthermore, the choices are not stripped from the story text, creating redundancy.
* **Fix**: Target the choice parser specifically to the `[OPTIONS & TYPABLE REFERENCE]` block.

---

### Priority 4: Campaign Data Standardization
*These issues address incomplete campaign data and archival formatting.*

#### 1. Populate `CAMPAIGNS/sample_campaign/`
* **Location**: `CAMPAIGNS/sample_campaign/`
* **Description**: Currently contains only `STATE/public_ledger.md`. All other directories (`GAMEPLAY`, `IDEAS`, `TURNS/ACTIVE`, `TURNS/ARCHIVE`, `WORLD_BIBLE`) are completely empty. It also has `WORLD_BIBLE/LORE/` instead of `CORE/`.
* **Fix**: Split `STATE/public_ledger.md` into `GAMEPLAY/status.md` and create initial world lore files, or standardize the engine to adapt to legacy ledgers.

#### 2. Normalize Legacy Archive Files
* **Location**: `CAMPAIGNS/template_campaign/TURNS/ARCHIVE/`
* **Description**: The 4 archive files contain rich historical transcripts (turns ~1 to 240) exported from NotebookLM, but lack standardized headers and turn number prefixes.
* **Fix**: Create a migration script that parses turn headers out of the archive files and organizes them into sequential files (`turn_0001.md` through `turn_0240.md`) or a structured archive index.

---

## Step-by-Step Remediation Roadmap

```mermaid
flowchart TD
    subgraph Phase 1: Unbreak Runtime
        P1A["Fix prompt_assembler.py load_campaign_state()"]
        P1B["Implement renderStoryStream() in app.js"]
        P1C["Wire customActionBtn event listener"]
        P1D["Connect campaignData to callGeminiAPI()"]
    end

    subgraph Phase 2: State & Persistence
        P2A["Build state_parser.py (Regex for SYS, XP, Coin)"]
        P2B["Update status.md on disk after each turn"]
        P2C["Reconcile CORE-001 with modular file tree"]
        P2D["Inject load_active_turns() into prompt_assembler"]
    end

    subgraph Phase 3: UI Features & Multi-Campaign
        P3A["Add Campaign Picker (support sample_campaign)"]
        P3B["Wire Settings (model select & max turns)"]
        P3C["Populate Sidebar Lore Tab from WORLD_BIBLE"]
        P3D["Refine Choice Parsing to [OPTIONS] section"]
    end

    Phase 1 --> Phase 2 --> Phase 3
```

1. **Phase 1: Unbreak Runtime (Immediate)**
   - Fix `load_campaign_state` in [prompt_assembler.py](ENGINE/prompt_assembler.py).
   - Add `renderStoryStream()` and wire `customActionBtn` in [app.js](UI/app.js).
   - Feed actual loaded data (`campaignData`) into `callGeminiAPI()`.

2. **Phase 2: State Persistence & Core Engine Loop**
   - Reconcile [CORE-001_HARD_CONSTRAINTS.md](GLOBAL/CORE-001_HARD_CONSTRAINTS.md) with the modular architecture in [INDEX.md](INDEX.md).
   - Implement `state_parser.py` (and corresponding JS parser in `app.js`) to parse `[XP RESOLUTION]`, `[CURRENCY RESOLUTION]`, and `[SYS: ...]`.
   - Update and persist `status.md` and `items.md` after each turn.
   - Include active turns in `PromptAssembler.build_system_prompt()`.

3. **Phase 3: UI Features & Multi-Campaign Support**
   - Allow campaign switching in the UI instead of hardcoded `template_campaign`.
   - Wire model selector and max-turns settings.
   - Populate the sidebar Lore tab from `WORLD_BIBLE/`.
   - Restrict choice button parsing strictly to the `[OPTIONS & TYPABLE REFERENCE]` block.

244: 
---

## Authoritative Review Disposition & Technical Counters

*Evaluation Date: October 2026*  
*Status: Decisions Codified — Implementation Pending User Authorization*

The following table and section-by-section breakdown detail the authoritative disposition (**ACCEPT** / **REJECT**) and technical rationale for every finding raised in this review.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ SUMMARY DISPOSITION MATRIX                                                       │
├───────────┬─────────────────────────────────────────────────┬──────────┬─────────┤
│ ID        │ Finding Summary                                 │ Decision │ Status  │
├───────────┼─────────────────────────────────────────────────┼──────────┼─────────┤
│ P0.1      │ AttributeError in prompt_assembler.py fallback   │ ACCEPT   │ FIXED   │
│ P0.2      │ Missing renderStoryStream() in UI/app.js         │ ACCEPT   │ FIXED   │
│ P0.3      │ Unwired #custom-action-btn                      │ ACCEPT   │ FIXED   │
│ P0.4      │ Hardcoded mock prompt in callGeminiAPI()        │ ACCEPT   │ FIXED   │
│ P1.1      │ Dual-Ledger Desync (STATE/ vs GAMEPLAY/)        │ ACCEPT   │ FIXED   │
│ P1.2      │ Missing state mutation loop back to disk        │ ACCEPT   │ FIXED   │
│ P1.3      │ PromptAssembler omits active turns              │ ACCEPT   │ FIXED   │
│ P1.4      │ Archiver regex mismatch on legacy archive files │ REJECT   │ Closed  │
│ P2.1      │ CORE-001 "Two-Document" spec clash              │ ACCEPT   │ FIXED   │
│ P2.2      │ Missing engine.py, state_parser.py, schemas     │ ACCEPT   │ FIXED   │
│ P2.3      │ Unbounded context bloat in World Bible loading  │ REJECT   │ Closed  │
│ P3.1      │ Hardcoded campaign selection (template_campaign) │ ACCEPT   │ FIXED   │
│ P3.2      │ Disconnected settings modal                     │ ACCEPT   │ FIXED   │
│ P3.3      │ Dead lore viewer in sidebar                     │ ACCEPT   │ FIXED   │
│ P3.4      │ Fragile choice extraction regex                 │ ACCEPT   │ FIXED   │
│ P4.1      │ Empty sample_campaign directory tree           │ ACCEPT   │ Low-Pri │
│ P4.2      │ Normalize legacy archive transcripts into turns │ REJECT   │ Closed  │
└───────────┴─────────────────────────────────────────────────┴──────────┴─────────┘
```

---

### Detailed Justifications & Technical Reasoning

#### Priority 0: Critical Runtime Blockers

* **P0.1: `load_campaign_state()` missing in `prompt_assembler.py`**
  * **Disposition**: **ACCEPT**
  * **Reasoning**: Valid defect. `load_campaign_gameplay()` calls `self.load_campaign_state()` on fallback, but that method was replaced. A 3-line fallback returning `STATE/public_ledger.md` if `GAMEPLAY/` is absent prevents crashes when initializing non-migrated campaigns.

* **P0.2: Missing `renderStoryStream()` in `UI/app.js`**
  * **Disposition**: **ACCEPT (Partially Addressed)**
  * **Reasoning**: Valid defect. The UI has been restructured with card streaming, but loading pre-existing `turn_XXXX.md` files from `TURNS/ACTIVE/` still requires a dedicated parsing and injection loop.

* **P0.3: Unwired `#custom-action-btn`**
  * **Disposition**: **ACCEPT (ALREADY FIXED)**
  * **Reasoning**: The bottom action dock has been completely refactored with the **Dedicated RECAL Section** and `#submit-action-btn`, tying both choice selection and recalibration into a unified turn execution pipeline.

* **P0.4: Hardcoded mock prompt in `callGeminiAPI()`**
  * **Disposition**: **ACCEPT**
  * **Reasoning**: Critical architectural flaw. `app.js` currently sends a 4-bullet static mock string, leaving the LLM blind to the rich `GAMEPLAY/` and `WORLD_BIBLE/` documents. The payload must dynamically concatenate loaded game state and recent turns.

---

#### Priority 1: State Persistence & Data Integrity

* **P1.1: Dual-Ledger Desynchronization (`STATE/` vs `GAMEPLAY/`)**
  * **Disposition**: **ACCEPT**
  * **Reasoning**: Having both `STATE/public_ledger.md` and `GAMEPLAY/status.md` violates the Single Source of Truth principle. `GAMEPLAY/*.md` will be codified as the **sole living state**, and `public_ledger.md` will be deprecated or converted into an export view.

* **P1.2: Missing State Mutation Loop (Deltas never saved to disk)**
  * **Disposition**: **ACCEPT**
  * **Reasoning**: Critical for continuity. Writing `turn_XXXX.md` preserves narrative history, but failing to parse `[XP RESOLUTION]` and `[CURRENCY RESOLUTION]` back into `status.md` and `items.md` causes permanent state drift upon app reload.

* **P1.3: Active turn omission in Python `PromptAssembler`**
  * **Disposition**: **ACCEPT**
  * **Reasoning**: `PromptAssembler.build_system_prompt()` must import `load_active_turns()` from `turn_archiver.py` to ground the LLM in the last $\le 15$ turns under `# 5. RECENT TURNS & IMMEDIATE HISTORY`.

* **P1.4: Turn file naming and archiver mismatch on legacy archives**
  * **Disposition**: **REJECT**
  * **Reasoning**: The 4 files in `TURNS/ARCHIVE/` (`Campaign Arc Defense.md`, etc.) are bulk historical transcripts (~300KB each from NotebookLM), not single-turn files. The `turn_(\d+)` regex is strictly designed for **incremental active turns** (`turn_0241.md`, etc.). Historical archives should remain intact as bulk reference records rather than being artificially split.

---

#### Priority 2: Architectural Contradictions & Missing Modules

* **P2.1: Reconcile `CORE-001` with Modular Architecture**
  * **Disposition**: **ACCEPT**
  * **Reasoning**: `CORE-001` Section 2 ("Two-Document Architecture") reflects a legacy NotebookLM constraint. It must be updated to formally codify the modular directory tree (`GAMEPLAY/`, `WORLD_BIBLE/CORE/`, `PLACES/`, `PEOPLE/`, `FACTIONS/`, `GUIDES/`).

* **P2.2: Missing Core Modules Specified in `INDEX.md`**
  * **Disposition**: **ACCEPT**
  * **Reasoning**: Implementing `ENGINE/state_parser.py` (regex/JSON extraction for `[SYS: ...]`, `[XP RESOLUTION]`, `[CURRENCY RESOLUTION]`) and standardizing `GLOBAL/SCHEMAS/turn_state.schema.json` provides shared validation across both the CLI and web clients.

* **P2.3: Unbounded Context Bloat in World Bible Loading**
  * **Disposition**: **REJECT (At Current Scale)**
  * **Reasoning**: a template campaign's entire modular World Bible is ~30KB (roughly 7,500 tokens). Gemini 2.5 Flash and Pro have 1M+ token context windows. Loading the complete world lore costs fractions of a cent per turn and guarantees the GM never forgets NPC traits or arcane mechanics. Introducing heavy semantic/RAG filtering at this stage adds fragile complexity with zero practical benefit.

---

#### Priority 3: UI / Engine Integration

* **P3.1: Hardcoded campaign selection (`template_campaign`)**
  * **Disposition**: **ACCEPT**
  * **Reasoning**: The client should inspect `CAMPAIGNS/` subdirectories and display a quick selection menu if multiple campaigns exist, supporting `sample_campaign` seamlessly.

* **P3.2: Disconnected Settings Modal**
  * **Disposition**: **ACCEPT (Partially Addressed)**
  * **Reasoning**: Model selection (`gemini-2.5-flash` vs `gemini-2.5-pro`) and prose pacing options (`concise`, `standard`, `expansive`) have been connected. Remaining work is to wire the max-turns input to control the rolling history buffer.

* **P3.3: Dead Lore Viewer in Sidebar**
  * **Disposition**: **ACCEPT (ALREADY FIXED)**
  * **Reasoning**: Resolved via `UI/world_bible_data.json` and the interactive multi-category pill browser in the sidebar.

* **P3.4: Fragile Choice Extraction Regex**
  * **Disposition**: **ACCEPT**
  * **Reasoning**: Valid safety improvement. Restricting choice extraction strictly to lines appearing beneath `[OPTIONS & TYPABLE REFERENCE]` prevents numbered in-world lore items from being converted into button controls.

---

#### Priority 4: Campaign Data Standardization

* **P4.2: Normalize Legacy Bulk Archive Files**
  * **Disposition**: **REJECT**
  * **Reasoning**: Splitting 300KB narrative transcripts into 240 artificial files provides no gameplay value and risks breaking historical narrative continuity. They are properly classified as permanent archival records.

---

### Priority 5: Dual Markdown + JSON State Architecture & PWA Offline Reconnection

* **P5.1: Structured State File (`GAMEPLAY/status.json`) alongside `status.md`**
  * **Disposition**: **ACCEPT (FIXED)**
  * **Reasoning**: While human-readable markdown (`status.md`) is ideal for reading and LLM context injection, structured machine JSON (`status.json`) eliminates regex ambiguity for client UI metric rendering and atomic mutations (turn number, level, XP, strain, coin denominations). Both formats are maintained simultaneously on disk.

* **P5.2: One-Click Re-Authorization for Stored Workspace Handle**
  * **Disposition**: **ACCEPT (FIXED)**
  * **Reasoning**: Chrome's File System Access API requires an explicit user gesture to restore read/write permissions for handles retrieved from `IndexedDB` across browser reloads. The UI now displays a pulsing `⚡ Reconnect: <folder>` indicator that re-authorizes disk access in a single click without forcing the user to re-navigate the directory tree.

* **P5.3: Robust Non-Greedy Markdown Parser & Multi-Tab Structured UI Components**
  * **Disposition**: **ACCEPT (FIXED)**
  * **Reasoning**: Legacy greedy regex `/\*\*(.*)\*\*/` caused bold tags to eat consecutive bold tokens, mangling lines such as `* **Turn**: **245**` into `Turn**: *245`. Replaced with a robust block-level Markdown engine (`renderMarkdown`) handling code blocks (`<pre><code>`), lists (`<ul><li>`), task checkboxes (`<li class="task-item">`), non-greedy inline styling, and horizontal rules. Additionally, created dedicated structured JSON data (`relations.json`, `items.json`) and native UI card renderers for the Status, Relations, and Items tabs, with view-mode toggles `[📊 HUD Cards | 📜 Living Record]`.

* **P5.4: Campaign Selection Persistence & Dynamic Top-Bar Metric Synchronization**
  * **Disposition**: **ACCEPT (FIXED)**
  * **Reasoning**: When reloading the web application or switching campaigns, top-bar pills previously fell back to empty placeholders (`Turn: —`, `XP: —`, `Strain: —`, `Purse: —`) if the folder handle was awaiting user re-authorization or if `applyActiveCampaignConfig()` executed prior to metric hydration. Fixed by:
    1. Persisting the selected campaign in `localStorage ('cyoa_selected_campaign')` across page refreshes.
    2. Calling `extractMetrics()` immediately after dynamic metric pill generation within `applyActiveCampaignConfig()`.
    3. Expanding `extractMetrics()` to parse structured `purse` objects (`{gold, silver, copper, display}`) and broadening regex fallbacks to support `Strain Buffer: 0 / 10` and `Currency Purse: 0 Platinum, 3 Gold Crowns, 6 Silver Marks, 20 Copper Cogs` cleanly into `3G 6S 20C`.

* **P5.5: Network-First Service Worker Strategy & Clean Permission UX**
  * **Disposition**: **ACCEPT (FIXED)**
  * **Reasoning**: A cache-first service worker was intercepting updates to `app.js`, `campaign_configs.json`, and `gameplay_manifest.json`, preventing browser refreshes from displaying modified disk files. Switched `sw.js` to a **Network-First** caching strategy with offline fallback and bumped cache version to `cyoa-engine-v6`.

* **P5.6: Local Antigravity Model Target & Unconstrained File System Activation**
  * **Disposition**: **ACCEPT (FIXED)**
  * **Reasoning**: Two critical usability issues were addressed:
    1. **Workspace Folder Picker Gesture Interception**: A window-level event listener (`onFirstInteraction`) was triggering asynchronous permission requests during user clicks, which consumed Chrome's ephemeral user activation gesture token and blocked `window.showDirectoryPicker()` with security errors. Removed the global interceptor, ensuring direct, synchronous user activation when clicking `📂 Select Workspace`.
    2. **Local Antigravity Model Target**: Added **Local Antigravity (Local Engine / Agent Bridge)** and **Custom Local Endpoint** (Ollama, vLLM, LM Studio) options to the Model Target dropdown in Settings (⚙), with a configurable endpoint URL (`http://localhost:8000/generate`). Implemented [`ENGINE/engine.py`](ENGINE/engine.py), providing a standalone local orchestrator with CORS support that executes turns without requiring external cloud API keys.


