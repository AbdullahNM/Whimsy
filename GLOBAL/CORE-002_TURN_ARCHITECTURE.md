# CORE-002: TURN, PACING & CONSEQUENCE ARCHITECTURE

## 1. The Turn Contract

Each turn resolves one meaningful player decision. A valid turn has five parts:

1. **Situation** — immediate, sensory, and limited to what the protagonist can know.
2. **Resolution** — causal outcome of the selected action, including opposition or uncertainty where appropriate.
3. **Persistent consequences** — changes to resources, clocks, flags, relationships, open threads, scene, or time.
4. **Choices** — 3–6 concise, distinct next actions, unless the scene is genuinely constrained.
5. **Resolution block** — out-of-character receipts and the next state summary.

The GM must not narrate an unearned success, assume a player statement or emotion, or invent a past action that the player did not take.

## 2. Resolution Procedure

For each selected option, record a compact resolution object before prose:

```text
intent: secure the quartermaster's cooperation
stakes: inspection begins before nightfall
cost: one favour owed to the quartermaster
outcome: partial_success
changes:
  - relations.quartermaster.standing: +1
  - flags.quartermaster_favour_owed: true
  - clocks.inspection: 2 -> 1
  - open_threads: add "Repay the quartermaster's favour"
```

The object is GM-facing implementation data. The player sees its consequences through prose, explicit receipts, and the public state—not raw internal reasoning.

## 3. Adaptive Narrative Focus & Pacing Architecture

Narrative camera zoom and pacing are governed by the **Adaptive Narrative Focus Controller** (`ENGINE/pacing_controller.py`). The engine dynamically scales time resolution based on active player intent, scene stakes, and operational tasks.

### 3.1 The Four Zoom Levels

1. **`detailed_scene` (Scene Scale / Turn-by-Turn)**:
   - High-sensory, continuous physical choreography.
   - Reserved for tactical combat, high-stakes negotiations, character confrontations, critical discoveries, and irreversible choices.
   - Narrative intensity scales from 2 to 5 depending on danger.

2. **`short_summary` (Local Compression / Day-Scale Leap)**:
   - Crisp, decisive summarization of uncomplicated local actions.
   - Used for short travel, simple errands, routine rest, or uncomplicated conversations that establish context without immediate tactical danger.
   - Narrative intensity maintains a quiet, grounded baseline (1 to 2).

3. **`montage` (Cycle-Scale / Thematic Compression)**:
   - Thematic compression across extended periods (days, weeks, or full routine cycles).
   - Used for routine training, extended journeys, workshop crafting, academic study, or seasonal work.
   - Presents meaningful resource allocations, routine progression receipts, and asks the player to direct scarce focus rather than living out uneventful hours step-by-step.

4. **`time_skip` (Discrete Milestone Leap)**:
   - Leaps forward to a specific scheduled milestone, pressure deadline, or arrival point.
   - Permitted only when no unresolved player intentions or immediate tactical threats remain active in the current scene.

### 3.2 Focus Evaluation & Player Autonomy

- **Routine Default**: Routine training, extended travel, chores, and downtime automatically default to `short_summary` or `montage` to prevent micro-stepping fatigue.
- **Player Zoom Directives**: Player intent explicitly commands camera focus:
  - *"zoom in"*, *"elaborate"*, *"in detail"*, *"step by step"* forces a `detailed_scene`.
  - *"skip to next morning"*, *"time skip"*, *"fast forward"* requests a `time_skip`.
  - *"montage"*, *"over the next few weeks"* requests a `montage`.
  - *"summarize"*, *"briefly"* requests a `short_summary`.

### 3.3 Transition Guard Rules (Anti-Degradation Gates)

Every state transition must satisfy deterministic gates in the `PacingController`:

1. **Unresolved Intentions Gate**: If the current scene contains active `unresolved_intentions`, the engine strictly blocks time skips (`time_skip` or elapsed minutes leap) and unearned departures unless the player explicitly grants permission or provides causal justification (e.g. aborting the mission, fleeing under fire).
2. **Dramatic Escalation Gate**: Narrative intensity cannot jump by more than **2 steps** on the 1–5 scale in a single transition (e.g. from 1 to 4 or 2 to 5) without explicit, diegetic causal justification (e.g. sudden ambush, structural catastrophe, catastrophic critical failure). Ordinary scenes must maintain low narrative intensity (1–2).
3. **Unearned Location Jump Gate**: Protagonists cannot teleport or instantaneously relocate between locations without narrative travel actions, passage of transit time, or causal transit events (e.g. portal, transport vehicle).
4. **Premature Resolution Gate**: Active conflicts and high-stakes opposition cannot be hand-waved or resolved without played choices, resource expenditure, or earned dice/skill challenges.

### 3.4 Explicit Time Accounting & Event Clocks

- **In-Game Time Arithmetic**: Time advances in discrete, explicit minutes (`elapsed_time_minutes`) tracked persistently in `pacing_state`.
- **Scheduled Event Clocks (`scheduled_events`)**:
  - Discrete world events configured with `id`, `trigger_time_minutes`, `description`, and `fired`.
  - When in-game time advancement crosses an event's trigger threshold, the event deterministically fires and is returned as a simulation event.
  - Triggered events take narrative precedence, interrupting long time skips or providing causal justification for scene transitions and intensity escalation.
- **Macro Hub Time Budgets**: Time-block hubs use explicit minutes deducted per selected activity until the budget is depleted.

## 4. Hubs

An open period may use a time-block hub. Establish a finite time budget and a stable menu of activities. Each activity has a stated time or resource cost. Once chosen, remove it, mark it completed, or show why it is no longer available; do not replace it with unrelated filler.

When the budget is exhausted, advance to the next pressure or scheduled event. Hub options must narrow rather than endlessly regenerate.

## 5. Campaign-Agnostic Progression and Economy

Progression systems are defined strictly by individual campaign configurations (`campaign_config.json`, `CONFIG.yaml`, and `AGENTS.md`). A campaign may use numeric XP, cultivation tiers, investigation clues, stress/sanity gauges, realm assets, or purely milestone checkpoints—or no numerical progression at all.

Regardless of the system used, the engine deterministically enforces the **Zero Micro-Scene Rule**:
- **Routine Scene Turns** (conversations, transit, meals, shopping, or low-intensity tasks): Award strictly `Delta: 0` advancement. Narrative agency, information discovery, items, and social developments are their own rewards.
- **Cycle Wind-Downs & Rest**: Routine advancement (e.g. daily cultivation or fatigue recovery) is awarded only at the closing turn of a full routine cycle or evening wind-down.
- **Event / Bout Advancement**: Advancement for challenges is awarded only upon completing an entire structured challenge phase or competitive trial.
- **Receipt Standard**: If a numerical metric changes, output an explicit itemized receipt:
  `[<METRIC> RESOLUTION: Previous: X | Delta: ±Y (Reason) | New Total: Z / Threshold]`
  (e.g., `[PROGRESSION/XP RESOLUTION: ...]`, `[DIVINITY RESOLUTION: ...]`, `[REALM RESOLUTION: ...]`).

Costs must be shown on the option that spends a player resource. Currency, supplies, fatigue, and social favours matter only if they restrict or enable future actions; avoid decorative accounting.

## 6. Required Public State

At the end of each turn, the public state must contain:

- current turn, timeline, and scene anchor;
- `pacing_state` containing current `scene_type`, `scene_objective`, `narrative_intensity` (1-5), `zoom_level`, `elapsed_time_minutes`, `timeline_stamp`, `unresolved_intentions`, `active_conflicts`, `current_location`, and `scheduled_events`;
- public resource changes;
- public clocks and their current values;
- flags or conditions the protagonist knows;
- open threads the player can act on next;
- the immediately available hooks.

GM-private plans, secret clocks, hidden identities, unrevealed traits, and future scene scripts must not enter public state.

## 7. Roadmaps

Campaign roadmaps are pressure maps, not scripts. They may define likely events, actors' goals, trigger conditions, and escalation consequences. They must not prescribe a player victory, romance, level-up, discovery, or exact turn number.

Write: “If the player ignores the canal reports, the smuggling clock advances.”

Never write: “At Turn 34 the player discovers the conspiracy and wins the fight.”

## 8. Chapter Closure

After a major resolution, provide one quiet drawing-close turn before an intermission. The drawing-close turn is diegetic and offers only reflection, recovery, or transition. The separate intermission handles save/checkpoint decisions and then begins the next chapter with a new scene.
