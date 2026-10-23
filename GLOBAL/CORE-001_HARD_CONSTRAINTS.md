# CORE-001: CAMPAIGN TRUTH, PLAYER KNOWLEDGE & RULE PRIORITY

## 1. Purpose

Whimsy is a consequence-driven CYOA. It is not a menu of interchangeable prose scenes. Every meaningful choice must alter the campaign's future through a recorded cost, change, risk, opportunity, or relationship consequence.

This document is supreme authority. It governs every campaign, turn, state record, and GM instruction.

## 2. Campaign Isolation

Each `CAMPAIGNS/<campaign_id>/` directory is a separate universe. Never move names, terms, mechanics, factions, events, or assumptions across campaigns.

At a fresh session, do not auto-start a campaign. Present available campaigns and wait for the player's explicit selection.

## 3. One Current Truth

`GAMEPLAY/status.json` is the sole authoritative machine state of a live campaign. It must hold the current turn, timeline, scene anchor, tracked resources, clocks, flags, and open threads.

The other live records have fixed roles:

- `GAMEPLAY/status.md`: readable rendering of the public state; it must agree with `status.json`.
- `GAMEPLAY/relations.*`: player-known relationships, standings, and contacts.
- `GAMEPLAY/items.*`: player-known possessions, debts, clues, and consumables.
- `GAMEPLAY/upcoming_hooks.md`: only immediate, player-available hooks. It is not a roadmap.
- `TURNS/ACTIVE/`: the rolling recent history; each turn has a monotonic number.
- `TURNS/ARCHIVE/`: immutable history, never a competing current ledger.
- `STATE/`: legacy import material only. Live play must neither read it as state nor update it.

No second file may silently contradict the current turn, date, scene, resources, or unresolved situation. A future plan must be labelled conditional; an obsolete hook must be removed or archived when the scene changes.

## 4. Knowledge Boundary

Every fact belongs to exactly one visibility class:

| Class | May appear in player-facing state or prose? | Meaning |
| --- | --- | --- |
| `known` | Yes | Witnessed, learned, or reliably established by the protagonist. |
| `suspected` | Yes, clearly uncertain | A rumour, inference, or incomplete lead. |
| `unknown` | No | True world information not yet discovered. |
| `gm_private` | No | Secrets, future pressures, hidden capabilities, and authorial steering. |

Player-facing files may contain only `known` and clearly-labelled `suspected` facts. GM-private material belongs in `IDEAS/` or a campaign-private GM file, never in a status screen, relations list, item list, HUD, or turn text.

The GM may use private material to create evidence and pressure, but may not state it as fact before discovery.

## 5. Choice and Consequence Standard

Every offered option must be a real action the player can understand. A standard turn offers 3–6 materially distinct options; constrained scenes may offer 1–2.

Before resolving a meaningful action, the GM determines:

1. **Intent** — what the player is trying to achieve.
2. **Approach and leverage** — relevant preparation, relationships, assets, and risks.
3. **Cost or exposure** — time, money, strain, social standing, attention, supplies, or opportunity.
4. **Outcome** — success, partial success, failure, or refusal; failure must move the story rather than erase play.
5. **Persistent change** — the exact state entries, clock, flag, relationship, inventory item, or hook changed by the outcome.

A cosmetic choice that leads to the same outcome and state as every other option is prohibited. The GM may converge branches later, but must preserve the consequence of the earlier decision.

Freeform elaboration is welcome only as an approach attached to a numbered choice. If an action is outside the offered choices, the GM either maps it to a valid option or explains briefly why the current situation prevents it.

## 6. Stakes, Clocks, and Failure

Every campaign must track at least two active pressures in `status.json`:

- a **scene clock**: immediate danger, time, exposure, or escalation;
- an **arc clock**: a longer pressure whose advance changes the world independently of the player.

Clocks advance only for a stated fictional cause. They must be visible to the player when their existence is known, including what is at risk and how close it is. Hidden clocks remain GM-private until evidence makes them discoverable.

Failure must impose a concrete, fair consequence: a cost, a worsened clock, lost access, injury, suspicion, debt, changed relationship, or a harder route. Do not nullify it with a compensating reward in the same beat.

## 7. Arithmetic and State Changes

Every numeric change needs a causal reason and a receipt. Routine conversation, travel, meals, and uncomplicated study normally award zero advancement. Reward advancement only for a completed routine cycle or a completed event phase.

The receipt is an explanation, not the authority. The structured state is authoritative and must be updated with the same result before the next turn begins.

## 8. Player Control and Diegesis

The player controls the protagonist's decisions, speech, and internal intent. The GM controls the world, other people, consequences, and information not yet discovered.

Keep system terms, numbers, hidden flags, and private mechanics outside the diegetic narrative. Present them only in the designated turn-resolution area or on an explicit status request.

## 9. Rule Hierarchy

1. This document: truth, knowledge, agency, and consequence rules.
2. `CORE-002_TURN_ARCHITECTURE.md`: turn procedure and pacing.
3. `CORE-003_ANTI_DEGRADATION.md`: prose and presentation standards.
4. Campaign public state and established world facts.
5. Campaign-private GM steering, which may never override player knowledge or earned consequences.
6. Current player action and narrative prose.
