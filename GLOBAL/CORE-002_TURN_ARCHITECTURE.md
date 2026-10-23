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

## 3. Pacing

Use scene-scale turns for danger, confrontations, discoveries, pivotal craft, negotiations, or decisions that create irreversible consequences.

Use a macro turn for ordinary routine. A macro turn covers a day, several days, or a week and asks the player to allocate a scarce focus among meaningful priorities. It must state what was deferred or worsened because that focus was not chosen.

Do not split travel, meals, gear preparation, or uncomplicated classroom attendance into standalone turns unless a choice there can change the campaign.

## 4. Hubs

An open period may use a time-block hub. Establish a finite time budget and a stable menu of activities. Each activity has a stated time or resource cost. Once chosen, remove it, mark it completed, or show why it is no longer available; do not replace it with unrelated filler.

When the budget is exhausted, advance to the next pressure or scheduled event. Hub options must narrow rather than endlessly regenerate.

## 5. Progression and Economy

Routine advancement is granted only at the closing turn of the relevant cycle. Event advancement is granted only when a defined phase has been completed. A receipt must show previous value, delta, cause, and new value.

Costs must be shown on the option that spends a player resource. Currency, supplies, fatigue, and social favours matter only if they restrict or enable future actions; avoid decorative accounting.

## 6. Required Public State

At the end of each turn, the public state must contain:

- current turn, timeline, and scene anchor;
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
