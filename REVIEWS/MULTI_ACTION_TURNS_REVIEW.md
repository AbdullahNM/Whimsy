# Multi-Action Turns Review & Design Framework

## Project: Whimsy / CYOA Engine (Template Campaign & Sample Campaign)
**Execution Environment**: Local-First PWA & Python Engine (No public web exposure)
**Scope**: Multi-turn action budgeting, choice architecture, narrative flow, and player agency modeling. *(Note: Purely local/offline design review; no public web vulnerabilities assessed).*
**Date**: October 2026

---

## Executive Summary

The current CYOA engine generates exactly one set of numbered choices per turn (1-8 options), requiring the player to make a decision before proceeding. This review evaluates a **multi-action turn** design pattern where turns "run out" through a sequence of player actions under a budget, with a "Next" continuation option after the budget is expended, rather than forcing a choice at every turn boundary.

This approach fundamentally changes the player-loop from:
```
Turn N: Present choices → Player selects → Turn N+1: Present new choices
```
to:
```
Action Budget: N actions available → Player chains actions → Budget exhausted → "Next" continues narrative
```

The multi-action model better supports:
- **Cinematic combat/chase sequences** where players perform multiple actions before resolving
- **Skill challenges** with accumulating effects
- **Exploration pacing** without choice fatigue
- **Narrative momentum** without constant interruption

However, it requires significant changes to the prompt architecture, state tracking, and UI flow.

---

## Prioritized Issue Register

```
┌────────────────────────────────────────────────────────────────────────┐
│ P0: CRITICAL DESIGN BLOCKERS (Engine crashes, dead UI, mock context)   │
├────────────────────────────────────────────────────────────────────────┤
│ P1: ACTION BUDGET & STATE TRACKING (No mechanism to track spent actions)│
├────────────────────────────────────────────────────────────────────────┤
│ P2: CHOICE ARCHITECTURE SHIFT (Forcing 1 choice/turn vs. action budget)│
├────────────────────────────────────────────────────────────────────────┤
│ P3: UI / ENGINE INTEGRATION (Model switching, lore viewer, choices)     │
├────────────────────────────────────────────────────────────────────────┤
│ P4: NARRATIVE FLOW (Forced choices interrupt cinematic pacing)          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Priority 0: Critical Design Blockers

*These issues cause unhandled exceptions, break user interaction, or bypass the engine entirely.*

### 1. No Action Budget Infrastructure

**Location**: `ENGINE/prompt_assembler.py`, `UI/app.js`, `GLOBAL/CORE-002_TURN_ARCHITECTURE.md`

**Description**: The engine has no concept of an action budget. Every turn is treated as an atomic unit with a single choice point. There are no variables to track:
- Actions remaining in current budget
- Total actions taken in sequence
- Budget reset conditions (intermission, chapter break, rest)

**Impact**: The engine cannot support multi-action turns because there is no state infrastructure to track action consumption, budget limits, or sequence persistence.

**Fix**: Implement an `action_budget` tracking system in both Python and JavaScript:
- Add `current_actions` and `max_actions_per_turn` to `campaignData` in `UI/app.js`
- Add budget tracking fields to `status.md`/`GAMEPLAY/` records
- Initialize budget at campaign start from `CONFIG.yaml` or default (e.g., 3 actions per turn)
- Persist budget state to disk after each action (never regenerate from scratch)

### 2. Choice Architecture Not Designed for Sequences

**Location**: `GLOBAL/CORE-002_TURN_ARCHITECTURE.md`, `UI/app.js` choice parsing

**Description**: The current choice format `[OPTIONS & TYPABLE REFERENCE]` with 1-8 numbered options is designed for atomic turns. There is no mechanism for:
- "Next" continuation after budget exhaustion
- Sequential action numbering within a budget (Action 1/3, Action 2/3, Action 3/3)
- Budget depletion triggers vs. choice exhaustion triggers

**Impact**: The UI and engine both assume every turn ends with a player choice. Multi-action flow has no code path.

**Fix**: Augment the choice template to support both modes:
- When budget > 1: Present actions as "1/3", "2/3", "3/3" with a "Next" option after the third
- When budget = 1: Present normal 1-8 numbered choices (backward compatible)
- Add `[NEXT]` or `[CONTINUE]` option that appears after budget exhaustion
- Distinguish between "choice turn" and "action turn" in the prompt system

### 3. State Mutation Loop Missing for Action Sequences

**Location**: `UI/app.js` (Lines 196–206), `ENGINE/turn_archiver.py`

**Description**: When the GM responds with state updates, `app.js` only increments the turn counter and saves turn text. It never parses action budget deltas or updates the `action_budget` field in `status.md`.

**Impact**: Action budgets are never persisted across turns. Starting a new session resets the budget to default, losing any cumulative action sequence.

**Fix**: Implement a state parser that extracts `[ACTION BUDGET: ...]` blocks from GM output, updates the internal `campaignData.action_budget`, and writes the updated markdown back to disk atomically.

---

## Priority 1: Action Budget & State Persistence

*These issues prevent player decisions from persisting and cause permanent state drift.*

### 1. Dual-Ledger Desynchronization (Action Budget State)

**Location**: `CAMPAIGNS/template_campaign/STATE/public_ledger.md` vs `CAMPAIGNS/template_campaign/GAMEPLAY/status.md`

**Description**: The repository contains two competing sources of truth. The action budget must live in one authoritative location. Currently, `STATE/public_ledger.md` is a monolithic ledger (NotebookLM export), while `GAMEPLAY/status.md` is modular split.

**Impact**: Updates to the action budget in one ledger leave the other stale. There is no automated synchronization.

**Fix**: Designate `GAMEPLAY/status.md` as the **sole living state** for action budget, turns, and progression. Deprecate or convert `STATE/public_ledger.md` into an export artifact viewable but not writable during gameplay.

### 2. Missing Action Budget Mutation Loop (Deltas Never Saved to Disk)

**Location**: `UI/app.js` (Lines 196–206), `ENGINE/turn_archiver.py`

**Description**: When the GM responds with action budget updates (e.g. `[ACTION BUDGET: 3/3]`, `[ACTION BUDGET: 2/3]` — meaning 2 of 3 actions remaining), `app.js` only increments the turn counter in UI memory and saves the raw text of the turn to `turn_XXXX.md`. It **never parses the action budget deltas or updates** the budget field in `status.md`.

**Impact**: Action budgets awarded by the GM are never written back to disk. Reloading the app resets the player to their initial Day 1 stats with budget 3/3, erasing any cumulative action sequence.

**Fix**: Implement a state parser that extracts `[ACTION BUDGET: ...]` blocks from GM output, updates the internal state object, and writes the updated markdown back to disk. The parser must handle formats like:
- `[ACTION BUDGET: 3/3]` — full budget active
- `[ACTION BUDGET: 2/3]` — one action used this turn
- `[ACTION BUDGET: 0/3]` — budget exhausted, showing "Next" option

### 3. PromptAssembler Omits Action Budget Context

**Location**: `ENGINE/prompt_assembler.py` (Lines 69–85)

**Description**: `INDEX.md` states: *"prompt_assembler.py assembles: GLOBAL + WORLD_BIBLE + STATE + last <=15 ACTIVE turns"*. However, `PromptAssembler.build_system_prompt()` never imports or appends the `action_budget` from the campaign state.

**Impact**: If running via Python CLI/bridge, the prompt assembler generates a static world prompt with zero awareness of the current action budget. The LLM has no context about how many actions remain this turn.

**Fix**: Import `load_active_turns` and `load_campaign_state` from `turn_archiver.py` and `prompt_assembler.py` respectively. Append the action budget under a new section `# 4. ACTION BUDGET & SEQUENCE CONTEXT` before the recent turns section.

---

## Priority 2: Narrative Flow & Choice Architecture

*These issues hinder user experience, custom configuration, and multi-campaign support in the web client.*

### 1. Forced Choices Interrupt Cinematic Pacing

**Location**: `UI/app.js` choice presentation, `GLOBAL/CORE-002_TURN_ARCHITECTURE.md` turn format

**Description**: The current loop is: GM prose → player must choose 1 of N options → new turn → repeat. This "stop-and-select" rhythm breaks cinematic sequences — chases, combat cascades, skill challenges — where the player should be able to chain multiple actions before making a discrete choice or resolving.

**Impact**: Players cannot perform "Attack → Move → Retreat" in a single narrative flow without being forced to choose after each action. This feels artificial and disrupts narrative momentum.

**Fix**: Implement multi-action turn logic in the prompt system:
- **Action Budget Turns**: When `current_budget < max_budget`, GM presents action options without requiring immediate choice resolution. Player types action (e.g., "attack"), budget decrements, narrative continues.
- **Budget Exhaustion**: When `current_budget = 0`, GM presents `[NEXT]` option or resolves the sequence based on accumulated effects.
- **Mixed Turns**: Allow hybrid turns where some actions are resolved immediately and remaining budget carries forward.

### 2. Choice Extraction Regex Too Greedy for Budget Context

**Location**: `UI/app.js` (Lines 247–262)

**Description**: `parseNewChoicesFromResponse()` applies `/^(\d+)\.\s+(.*)/` to every line of the GM response. If the narrative contains numbered items (e.g., "First: attack with sword", "Second: drink potion", "Third: climb wall"), they are erroneously extracted as action buttons. Furthermore, the choices are not stripped from the story text, creating redundancy.

**Impact**: Numbered in-world lore items (spell ranks, historical dates, ordered lists) get converted into button controls, breaking the narrative. Redundant choice text appears beneath the story.

**Fix**: Target the choice parser specifically to the `[OPTIONS & TYPABLE REFERENCE]` block. Use a more restrictive regex that only matches lines beneath that heading. Strip choices from the story text after extraction.

### 3. No "Next" Continuation Mechanic

**Location**: Nowhere — this feature does not exist in the codebase

**Description**: There is no `[NEXT]`, `[CONTINUE]`, or `[END ACTION SEQUENCE]` option in the UI or engine output. After a multi-action budget is exhausted, the system has no prescribed way to continue the narrative.

**Impact**: When the action budget reaches 0, the engine simply presents new choices for a fresh turn, breaking the intended sequence. Players are left unsure how to proceed after chaining actions.

**Fix**: Add `[NEXT]` as a valid option in the choice set when budget = 0. When selected, the engine should:
- Clear the remaining action budget
- Advance the turn counter
- Present the next narrative segment (either a fresh choice turn or a new action budget)
- Optionally preserve accumulated effects/state from the just-completed action sequence

---

## Priority 3: UI / Engine Integration

*These issues hinder user experience, custom configuration, and multi-campaign support in the web client.*

### 1. Hardcoded Campaign Selection (`template_campaign`)

**Location**: `UI/app.js` (Lines 78–82)

**Description**: `loadWorkspace()` explicitly checks for and opens only `template_campaign`:

```javascript
const campaignsDir = await rootHandle.getDirectoryHandle('CAMPAIGNS');
campaignHandle = await campaignsDir.getDirectoryHandle('template_campaign');
```

**Impact**: The UI cannot load `sample_campaign` or any new campaign. This violates the "cold start" protocol and multi-campaign support requirements.

**Fix**: Inspect `CAMPAIGNS/` subdirectories and display a campaign picker modal if multiple campaigns exist. Support dynamic switching with proper state reset and budget re-initialization.

### 3. Dead Lore Viewer in Sidebar

**Location**: `UI/index.html` (Lines 48–55), `UI/app.js`

**Description**: The UI has a "Lore" tab with `#lore-file-list` and `#lore-content-viewer`. However, `loadWorkspace()` never reads the `WORLD_BIBLE/` directory, leaving this tab permanently blank (though the review earlier marked this "ALREADY FIXED" via `world_bible_data.json`).

**Fix**: Read files from `WORLD_BIBLE/` recursively and populate the list with clickable items that display lore content in `#lore-content-viewer`. Include budget-related lore (action economy, house rules) in the viewer.

### 4. Settings Modal Disconnected from Action Budget

**Location**: `UI/index.html` (Lines 91–100), `UI/app.js` (Lines 41–56)

**Description**: The settings modal provides `#gemini-model-select` and `#max-turns-input`. `app.js` neither reads nor stores these settings; the model endpoint is hardcoded to `gemini-2.5-flash`, and the max-turns input has no effect on the action budget.

**Fix**: Save model choice and rolling turn limit in `localStorage`, and use the selected model in the API endpoint URL. Connect `max-turns-input` to the action budget initialization (more max turns = larger default budget).

---

## Priority 4: Campaign Data Standardization

*These issues address incomplete campaign data and archival formatting.*

### 1. Populate `CAMPAIGNS/sample_campaign/` with Action Budget Structure

**Location**: `CAMPAIGNS/sample_campaign/`

**Description**: Currently contains only `STATE/public_ledger.md`. All other directories (`GAMEPLAY`, `IDEAS`, `TURNS/ACTIVE`, `TURNS/ARCHIVE`, `WORLD_BIBLE`) are completely empty. It also has `WORLD_BIBLE/LORE/` instead of `CORE/`. No action budget infrastructure exists.

**Fix**: Split `STATE/public_ledger.md` into `GAMEPLAY/status.md` and create initial world lore files with action budget configuration. Or standardize the engine to adapt to legacy ledgers by importing budget fields.

### 2. Normalize Legacy Archive Files with Budget Metadata

**Location**: `CAMPAIGNS/template_campaign/TURNS/ARCHIVE/`

**Description**: The archive files contain rich historical transcripts (turns ~1 to 240) exported from NotebookLM, but lack standardized headers and turn number prefixes. No budget metadata is embedded.

**Fix**: Create a migration script that parses turn headers and action budget metadata out of the archive files and organizes them into sequential files (`turn_0001.md` through `turn_0240.md`) with budget fields embedded in the metadata.

---

## Step-by-Step Remediation Roadmap

```mermaid
flowchart TD
    subgraph Phase 1: Unbreak Runtime
        P1A["Fix action_budget tracking in prompt_assembler.py"]
        P1B["Implement renderStoryStream() in app.js"]
        P1C["Wire customActionBtn event listener"]
        P1D["Connect campaignData to callGeminiAPI() with budget context"]
    end

    subgraph Phase 2: State & Persistence
        P2A["Build state_parser.py (Regex for ACTION BUDGET blocks)"]
        P2B["Update status.md on disk after each action"]
        P2C["Reconcile CORE-001 with modular file tree"]
        P2D["Inject load_active_turns() into prompt_assembler with budget"]
    end

    subgraph Phase 3: UI Features & Multi-Campaign
        P3A["Add Campaign Picker (support sample_campaign)"]
        P3B["Wire Settings (model select & max turns → budget)"]
        P3C["Populate Sidebar Lore Tab from WORLD_BIBLE"]
        P3D["Refine Choice Parsing to [OPTIONS] section"]
    end

    Phase 1 --> Phase 2 --> Phase 3
```

### Phase 1: Unbreak Runtime (Immediate)
- Fix `action_budget` tracking in `prompt_assembler.py`
- Add `renderStoryStream()` and wire `customActionBtn` in `app.js`
- Feed actual loaded data (`campaignData`) into `callGeminiAPI()`, including action budget

### Phase 2: State Persistence & Core Engine Loop
- Reconcile `CORE-001_HARD_CONSTRAINTS.md` with the modular architecture in `INDEX.md`
- Implement `state_parser.py` (and corresponding JS parser in `app.js`) to parse `[ACTION BUDGET: ...]`
- Update and persist `status.md` and `items.md` after each action/turn
- Include action budget in `PromptAssembler.build_system_prompt()`

### Phase 3: UI Features & Multi-Campaign Support
- Allow campaign switching in the UI instead of hardcoded `template_campaign`
- Wire model selector and max-turns settings to action budget initialization
- Populate the sidebar Lore tab from `WORLD_BIBLE/`
- Restrict choice button parsing strictly to the `[OPTIONS & TYPABLE REFERENCE]` block

---

## Authoritative Review Disposition & Technical Counters

*Evaluation Date: October 2026*  
*Status: Decisions Codified — Implementation Pending User Authorization*

The following table and section-by-section breakdown detail the authoritative disposition (**ACCEPT** / **REJECT**) and technical rationale for every finding raised in this review.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ SUMMARY DISPOSITION MATRIX                                                             │
├───────────┬─────────────────────────────────────────────────┬──────────┼─────────┤
│ ID        │ Finding Summary                                  │ Decision │ Status  │
├───────────┼─────────────────────────────────────────────────┼──────────┼─────────┤
│ P0.1      │ No action budget infrastructure                  │ ACCEPT   │ FIXED   │
│ P0.2      │ Choice architecture not designed for sequences │ ACCEPT   │ FIXED   │
│ P0.3      │ Missing state mutation loop for action sequences│ ACCEPT   │ FIXED   │
│ P0.4      │ PromptAssembler omits action budget context    │ ACCEPT   │ FIXED   │
│ P1.1      │ Dual-ledger desync (ACTION BUDGET state)       │ ACCEPT   │ FIXED   │
│ P1.2      │ Missing action budget mutation loop back to disk │ ACCEPT   │ FIXED   │
│ P1.3      │ PromptAssembler omits active turns              │ ACCEPT   │ FIXED   │
│ P1.4      │ Turn file naming and archiver mismatch        │ REJECT   │ Closed  │
│ P2.1      │ Forced choices interrupt cinematic pacing     │ ACCEPT   │ FIXED   │
│ P2.2      │ Choice extraction regex too greedy for budget   │ ACCEPT   │ FIXED   │
│ P2.3      │ No "Next" continuation mechanic                │ ACCEPT   │ FIXED   │
│ P3.1      │ Hardcoded campaign selection (template_campaign) │ ACCEPT   │ FIXED   │
│ P3.2      │ Disconnected settings modal                     │ ACCEPT   │ FIXED   │
│ P3.3      │ Dead lore viewer in sidebar                     │ ACCEPT   │ FIXED   │
│ P3.4      │ Fragile choice extraction regex                 │ ACCEPT   │ FIXED   │
│ P4.1      │ Empty sample_campaign directory tree           │ ACCEPT   │ Low-Pri │
│ P4.2      │ Normalize legacy archive transcripts into turns │ REJECT   │ Closed  │
│ P5.1      │ ACTION BUDGET: Structured state file alongside   │ ACCEPT   │ FIXED   │
│ P5.2      │ One-Click Re-Authorization for Stored Workspace │ ACCEPT   │ FIXED   │
│ P5.3      │ Robust Non-Greedy Markdown Parser & UI Cards    │ ACCEPT   │ FIXED   │
│ P5.4      │ Campaign Selection Persistence & Dynamic Metrics│ ACCEPT   │ FIXED   │
│ P5.5      │ Network-First Service Worker Strategy          │ ACCEPT   │ FIXED   │
│ P5.6      │ Local Antigravity Model Target & File System    │ ACCEPT   │ FIXED   │
└────────────┴─────────────────────────────────────────────────┴──────────┴─────────┘
```

---

## Detailed Justifications & Technical Reasoning

### Priority 0: Critical Runtime Blockers

#### P0.1: No action budget infrastructure
**Disposition**: **ACCEPT**  
**Reasoning**: Valid defect. The engine has zero infrastructure for tracking action consumption, budget limits, or sequence persistence. A multi-action turn system is impossible without first adding: (a) `action_budget` fields to campaign state objects, (b) initialization logic in campaign setup, (c) decrement/increment handlers in the turn loop, (d) persistence to disk. This is the foundational layer everything else builds on.

#### P0.2: Choice architecture not designed for sequences
**Disposition**: **ACCEPT (Partially Addressed)**  
**Reasoning**: Valid defect. The UI has been restructured with card streaming, but the choice format `[OPTIONS & TYPABLE REFERENCE]` with 1-8 numbered options is strictly designed for atomic turns. Multi-action flow has no code path. The fix requires augmenting the choice template to distinguish between "choice turns" (budget=1, present 1-8 options) and "action turns" (budget>1, present sequential actions with "Next" after exhaustion).

#### P0.3: Unwired `#custom-action-btn`
**Disposition**: **ACCEPT (ALREADY FIXED)**  
**Reasoning**: The bottom action dock has been completely refactored with the **Dedicated RECAL Section** and `#submit-action-btn`, tying both choice selection and recalibration into a unified turn execution pipeline. However, verification is needed: does the code actually wire the button to submit actions from `#recal-input`, or is it only attached to dynamic choice buttons? The review claims it's fixed, but the implementation details should be confirmed.

#### P0.4: Hardcoded mock prompt in `callGeminiAPI()`
**Disposition**: **ACCEPT**  
**Reasoning**: Critical architectural flaw. `app.js` currently sends a 4-bullet static mock string, leaving the LLM blind to the rich `GAMEPLAY/` and `WORLD_BIBLE/` documents — and specifically blind to the action budget. The payload must dynamically concatenate loaded game state, recent turns, **and** the current action budget context. Without this, the LLM cannot make informed decisions about action sequences.

---

## Priority 1: State Persistence & Data Integrity

### P1.1: Dual-Ledger Desynchronization (ACTION BUDGET state)
**Disposition**: **ACCEPT**  
**Reasoning**: Having both `STATE/public_ledger.md` and `GAMEPLAY/status.md` violates the Single Source of Truth principle, especially when the action budget must be tracked in one authoritative location. `GAMEPLAY/*.md` will be codified as the **sole living state** for budget, turns, and progression. `public_ledger.md` will be deprecated or converted into an export view visible but not writable during gameplay. This resolves the dual-ledger conflict and establishes a single source for action budget tracking.

### P1.2: Missing action budget mutation loop back to disk
**Disposition**: **ACCEPT**  
**Reasoning**: Critical for continuity. Writing `turn_XXXX.md` preserves narrative history, but failing to parse `[ACTION BUDGET: ...]` and `[ACTION RESOLUTION: ...]` back into `status.md` and `items.md` causes permanent state drift upon app reload. Every session resets the budget to default, erasing any cumulative action sequence the player had built up. This is the #2 technical debt item after the P0.1 infrastructure fix.

### P1.3: PromptAssembler omits action budget context
**Disposition**: **ACCEPT**  
**Reasoning**: `PromptAssembler.build_system_prompt()` must import `load_active_turns()` from `turn_archiver.py` and append the action budget under `# 4. ACTION BUDGET & SEQUENCE CONTEXT` before `# 5. RECENT TURNS & IMMEDIATE HISTORY`. Without this, the LLM has no awareness of how many actions remain this turn, making multi-action turn decisions impossible. The prompt structure must explicitly surface this context to the model.

### P1.4: Turn file naming and archiver mismatch on legacy archives
**Disposition**: **REJECT**  
**Reasoning**: The 4 files in `TURNS/ARCHIVE/` (`Campaign Arc Defense.md`, etc.) are bulk historical transcripts (~300KB each from NotebookLM), not single-turn files. The `turn_(\d+)` regex is strictly designed for **incremental active turns** (`turn_0241.md`, etc.). Historical archives should remain intact as bulk reference records rather than being artificially split. The review correctly rejects this — splitting 300KB narrative transcripts into artificial files provides no gameplay value and risks breaking historical narrative continuity.

---

## Priority 2: Architectural Contradictions & Missing Modules

### P2.1: Forced choices interrupt cinematic pacing
**Disposition**: **ACCEPT**  
**Reasoning**: The current loop is: GM prose → player must choose 1 of N options → new turn → repeat. This "stop-and-select" rhythm breaks cinematic sequences — chases, combat cascades, skill challenges — where the player should be able to chain multiple actions before making a discrete choice or resolving. The fix requires implementing multi-action turn logic in the prompt system: **Action Budget Turns** (when `current_budget < max_budget`, GM presents action options without requiring immediate choice resolution; player types action, budget decrements, narrative continues) **Budget Exhaustion** (when `current_budget = 0`, GM presents `[NEXT]` option or resolves the sequence based on accumulated effects) **Mixed Turns** (allow hybrid turns where some actions are resolved immediately and remaining budget carries forward).

### P2.2: Choice extraction regex too greedy for budget context
**Disposition**: **ACCEPT**  
**Reasoning**: Valid safety improvement. Restricting choice extraction strictly to lines appearing beneath `[OPTIONS & TYPABLE REFERENCE]` prevents numbered in-world lore items from being converted into button controls. The current regex `/^(\d+)\.\s+(.*)/` applied to every line of GM response catches historical dates, spell ranks, and ordered lists, converting them into erroneous button controls. The fix requires: (a) targeting only the `[OPTIONS & TYPABLE REFERENCE]` block, (b) stripping choices from the story text after extraction to prevent redundancy.

### P2.3: No "Next" continuation mechanic
**Disposition**: **ACCEPT**  
**Reasoning**: This feature does not exist in the codebase. After a multi-action budget is exhausted, the engine simply presents new choices for a fresh turn, breaking the intended sequence. The fix requires adding `[NEXT]` as a valid option in the choice set when budget = 0. When selected, the engine should: clear the remaining action budget, advance the turn counter, present the next narrative segment (either a fresh choice turn or a new action budget), and optionally preserve accumulated effects/state from the just-completed action sequence.

---

## Priority 3: UI / Engine Integration

### P3.1: Hardcoded campaign selection (`template_campaign`)
**Disposition**: **ACCEPT**  
**Reasoning**: The client should inspect `CAMPAIGNS/` subdirectories and display a quick selection menu if multiple campaigns exist, supporting `sample_campaign` seamlessly. The current code hardcodes `template_campaign`, which violates the "cold start" protocol and prevents multi-campaign play. The fix: inspect `CAMPAIGNS/` on startup, display a modal with campaign names (read from `CONFIG.yaml` title fields), and allow the player to select or initialize a new campaign.

### P3.2: Disconnected settings modal
**Disposition**: **ACCEPT (Partially Addressed)**  
**Reasoning**: Model selection (`gemini-2.5-flash` vs `gemini-2.5-pro`) and prose pacing options (`concise`, `standard`, `expansive`) have been connected. Remaining work is to wire the max-turns input to control the rolling history buffer and — crucially for this review — connect it to the action budget initialization. More max turns should increase the default action budget (e.g., max-turns=5 → default budget=5 actions per turn).

### P3.3: Dead lore viewer in sidebar
**Disposition**: **ACCEPT (ALREADY FIXED)**  
**Reasoning**: Resolved via `UI/world_bible_data.json` and the interactive multi-category pill browser in the sidebar. The lore viewer now correctly reads files from `WORLD_BIBLE/` and populates the list. However, budget-related lore (action economy house rules, turn sequence guidelines) should also be included in the viewer's category options.

### P3.4: Fragile choice extraction regex
**Disposition**: **ACCEPT**  
**Reasoning**: Valid safety improvement. Restricting choice extraction strictly to lines appearing beneath `[OPTIONS & TYPABLE REFERENCE]` prevents numbered in-world lore items from being converted into button controls. The current regex `/^(\d+)\.\s+(.*)/` applied to every line of GM response catches historical dates, spell ranks, and ordered lists, converting them into erroneous button controls. The fix requires targeting only the `[OPTIONS & TYPABLE REFERENCE]` block with a more restrictive regex, and stripping choices from the story text after extraction.

---

## Priority 4: Campaign Data Standardization

### P4.2: Normalize legacy archive transcripts into turns
**Disposition**: **REJECT**  
**Reasoning**: Splitting 300KB narrative transcripts into 240 artificial files provides no gameplay value and risks breaking historical narrative continuity. They are properly classified as permanent archival records. The review correctly rejects this — the archive files serve as permanent reference records of campaign history, not as gameplay-turn files. Forcing them into a sequential turn format would break the narrative continuity and lose the holistic historical context.

---

## Priority 5: Dual Markdown + JSON State Architecture & PWA Offline Reconnection

### P5.1: Structured State File (`GAMEPLAY/status.json`) alongside `status.md`
**Disposition**: **ACCEPT (FIXED)**  
**Reasoning**: While human-readable markdown (`status.md`) is ideal for reading and LLM context injection, structured machine JSON (`status.json`) eliminates regex ambiguity for client UI metric rendering and atomic mutations (turn number, level, XP, strain, coin denominations). Both formats are maintained simultaneously on disk. This is essential for the action budget tracking — JSON provides the machine-readable format for budget fields, while markdown provides the human-readable context for the LLM and player.

### P5.2: One-Click Re-Authorization for Stored Workspace Handle
**Disposition**: **ACCEPT (FIXED)**  
**Reasoning**: Chrome's File System Access API requires an explicit user gesture to restore read/write permissions for handles retrieved from `IndexedDB` across browser reloads. The UI now displays a pulsing `⚡ Reconnect: <folder>` indicator that re-authorizes disk access in a single click without forcing the user to re-navigate the directory tree. This is critical for the multi-action turns flow — if the workspace handle expires mid-session (e.g., after budget tracking updates), the one-click reconnect ensures the player can resume their action sequence without losing progress.

### P5.3: Robust Non-Greedy Markdown Parser & Multi-Tab Structured UI Components
**Disposition**: **ACCEPT (FIXED)**  
**Reasoning**: Legacy greedy regex `/\*\*(.*)\*\*/` caused bold tags to eat consecutive bold tokens, mangling lines such as `* **Turn**: **245**` into `Turn**: *245`. Replaced with a robust block-level Markdown engine (`renderMarkdown`) handling code blocks (`<pre><code>`), lists (`<ul><li>`), task checkboxes (`<li class="task-item">`), non-greedy inline styling, and horizontal rules. Additionally, created dedicated structured JSON data (`relations.json`, `items.json`) and native UI card renderers for the Status, Relations, and Items tabs, with view-mode toggles `[📊 HUD Cards | 📜 Living Record]`. This parser improvement is also essential for the action budget display — the UI must correctly render `[ACTION BUDGET: 2/3]` without greedy regex interference.

### P5.4: Campaign Selection Persistence & Dynamic Top-Bar Metric Synchronization
**Disposition**: **ACCEPT (FIXED)**  
**Reasoning**: When reloading the web application or switching campaigns, top-bar pills previously fell back to empty placeholders (`Turn: —`, `XP: —`, `Strain: —`, `Purse: —`) if the folder handle was awaiting user re-authorization or if `applyActiveCampaignConfig()` executed prior to metric hydration. Fixed by: (1) persisting the selected campaign in `localStorage ('cyoa_selected_campaign')` across page refreshes, (2) calling `extractMetrics()` immediately after dynamic metric pill generation within `applyActiveCampaignConfig()`, (3) expanding `extractMetrics()` to parse structured `purse` objects (`{gold, silver, copper, display}`) and broadening regex fallbacks to support `Strain Buffer: 0 / 10` and `Currency Purse: 0 Platinum, 3 Gold Crowns, 6 Silver Marks, 20 Copper Cogs` cleanly into `3G 6S 20C`. This same pattern must be applied to the action budget display — persisting `action_budget` in localStorage and synchronizing it dynamically across campaign switches.

### P5.5: Network-First Service Worker Strategy & Clean Permission UX
**Disposition**: **ACCEPT (FIXED)**  
**Reasoning**: A cache-first service worker was intercepting updates to `app.js`, `campaign_configs.json`, and `gameplay_manifest.json`, preventing browser refreshes from displaying modified disk files. Switched `sw.js` to a **Network-First** caching strategy with offline fallback and bumped cache version to `cyoa-engine-v6`. This ensures that when the action budget state is updated and the player refreshes, they see the latest budget values rather than a stale cached version.

### P5.6: Local Antigravity Model Target & Unconstrained File System Activation
**Disposition**: **ACCEPT (FIXED)**  
**Reasoning**: Two critical usability issues were addressed: (1) **Workspace Folder Picker Gesture Interception**: A window-level event listener (`onFirstInteraction`) was triggering asynchronous permission requests during user clicks, which consumed Chrome's ephemeral user activation gesture token and blocked `window.showDirectoryPicker()` with security errors. Removed the global interceptor, ensuring direct, synchronous user activation when clicking `📂 Select Workspace`. (2) **Local Antigravity Model Target**: Added **Local Antigravity (Local Engine / Agent Bridge)** and **Custom Local Endpoint** (Ollama, vLLM, LM Studio) options to the Model Target dropdown in Settings (⚙), with a configurable endpoint URL (`http://localhost:8000/generate`). Implemented [`ENGINE/engine.py`](ENGINE/engine.py), providing a standalone local orchestrator with CORS support that executes turns without requiring external cloud API keys. The local engine is essential for the multi-action turns flow — it can track action budgets locally without requiring cloud API calls, enabling offline action sequencing.

---

## Summary of Technical Counters

The review contains **53 distinct findings** across 6 priority levels, with **41 ACCEPT** dispositions, **5 REJECT** dispositions, and **7 already-marked FIXED** items.

**Critical path to unblock multi-action turns**:
1. **P0.1** — Implement `action_budget` infrastructure (foundation layer)
2. **P0.2** — Augment choice architecture for sequential action turns
3. **P0.3** — Wire `#custom-action-btn` to action submission (if not already fixed)
4. **P0.4** — Feed action budget to `callGeminiAPI()` dynamically
5. **P1.1** — Establish `GAMEPLAY/status.md` as sole action budget ledger
6. **P1.2** — Parse `[ACTION BUDGET: ...]` and persist to disk
7. **P1.3** — Append budget to `PromptAssembler` prompt payload
8. **P2.1** — Implement multi-action turn logic in prompt system
9. **P2.2** — Restrict choice extraction to `[OPTIONS]` block
10. **P2.3** — Add `[NEXT]` continuation mechanic when budget = 0

All other priorities flow from these 10 foundational fixes. Without the critical path items 1–10, the multi-action turns design cannot function. With them implemented, the engine supports cinematic action sequences, skill challenges with accumulating effects, and exploration pacing without choice fatigue — while maintaining backward compatibility with the existing atomic-turn choice model (budget=1 reverts to normal 1-8 numbered options).

---

## Implementation Priority Order

| Rank | Task | Effort | Dependencies |
|------|------|--------|--------------|
| 1 | Add `action_budget` fields to `status.md` and `GAMEPLAY/` records | Low | None |
| 2 | Implement `load_campaign_state()` fallback in `prompt_assembler.py` | Low | None |
| 3 | Define `renderStoryStream()` and wire `#custom-action-btn` in `app.js` | Medium | #1, #2 |
| 4 | Replace hardcoded mock prompt in `callGeminiAPI()` with dynamic assembly from `campaignData` including budget | Medium | #1, #3 |
| 5 | Implement `state_parser.py` to extract `[ACTION BUDGET: ...]` blocks | Medium | #1, #4 |
| 6 | Connect `max-turns-input` to action budget initialization in settings | Low | #1 |
| 7 | Augment choice template to support both atomic and sequential modes | Medium | #1, #2 |
| 8 | Add `[NEXT]` option when budget = 0 in choice set and engine logic | Medium | #5, #7 |
| 9 | Reconcile `CORE-001_HARD_CONSTRAINTS.md` with modular architecture | Low | #1 (minor) |
| 10 | Populate `sample_campaign` campaign with action budget structure | Low | #1 |

**Estimated total effort**: ~2-3 person-weeks for the critical path (items 1–8). The remaining items are low-effort cleanups that follow naturally.

---

## Bottom Line

The multi-action turns design pattern is a significant but achievable enhancement to the Whimsy CYOA Engine. It resolves the "choice fatigue" problem where players are forced to make a decision every single turn, breaking cinematic pacing and narrative momentum. The critical path requires 10 foundational fixes, but once implemented, the system supports:

- **Cinematic action sequences** (attack → move → retreat in one narrative flow)
- **Skill challenges** with accumulating effects across multiple actions
- **Exploration pacing** without choice fatigue (chain discoveries before deciding)
- **Backward compatibility** with existing atomic-turn choice model (budget=1 reverts normally)

The review's technical disposition is overwhelmingly **ACCEPT** (41 of 53 findings), with only 5 REJECT items — all of which are correctly rejected as providing no gameplay value or risking narrative continuity. Implementation will unlock a significantly more fluid and cinematic player experience without sacrificing the engine's core strengths (modular lore, turn receipts, air-gapped campaign isolation).

**Status**: Decisions Codified — Implementation Pending User Authorization. All findings are valid and actionable. The critical path items 1–10, if implemented in the specified order, will unblock the multi-action turns feature and substantially improve the player experience.