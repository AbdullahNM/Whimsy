# Whimsy Campaign Contract

Every playable campaign must satisfy this contract before it is marked active.

## Required campaign assets

- A public current state in `GAMEPLAY/status.json` and a matching readable `status.md`.
- Public relationships, inventory, open threads, and immediate hooks.
- A campaign directive that defines tone, prohibited register, protagonist scope, and any genre-specific resolution rules.
- At least two pressures: one scene clock and one arc clock.
- A private steering document containing conditional pressures, never a predetermined player story.
- An opening or current turn with a concrete situation and 3–6 materially distinct choices.

## State-field contract

New campaigns should include these `status.json` fields. Existing campaigns may migrate incrementally.

```json
{
  "schema_version": 2,
  "campaign_id": "campaign_name",
  "turn": 1,
  "timeline": "Day 1, morning",
  "progression": {
    "checkpoint_tokens": 5,
    "checkpoint_max": 5
  },
  "scene_anchor": {"location": "", "context": "", "time": ""},
  "public_state": {
    "flags": {},
    "conditions": [],
    "open_threads": []
  },
  "clocks": [
    {"id": "scene_pressure", "label": "Known pressure", "current": 0, "max": 4, "visibility": "known", "advance_trigger": ""},
    {"id": "arc_pressure", "label": "Long-term pressure", "current": 0, "max": 6, "visibility": "known", "advance_trigger": ""}
  ]
}
```

Only `known` and clearly labelled `suspected` data belongs in this file. Private facts use `IDEAS/` and must carry a visibility label when referenced.

## Turn-quality gate

Before presenting a turn, verify:

1. Does the action have stakes and a possible cost?
2. Does the resolution change at least one persistent fact when the action is meaningful?
3. Are the resulting choices different in objective, cost, risk, or future availability?
4. Is any revealed information within the protagonist's knowledge?
5. Could routine material have been summarized instead?

If any answer is no, revise the turn before presenting it.
