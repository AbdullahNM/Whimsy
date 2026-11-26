# NARRATIVE STEERING — THE CINDER LEDGER (GM-PRIVATE)

> **CONFIDENTIALITY**: This document is strictly GM-private (Shadow Narrator & Active GM reference only). Never expose hidden triggers, unrevealed canon secrets, or future roadmaps into `GAMEPLAY/` or unearned NPC dialogue.

---

## 1. 50–100 Turn Macro Arc Compass (Pressure Map, Not Script)

### Horizon I: The Dawn Audit & Pier Seven (Turns 1–15)
- **Current Turning Point (Turn 6)**: Corin has completed the initial Pier Seven Inspection phase (+25 XP), recovering the **Cinder Ledger** (`#P7-088` stub), **Elena Reed**'s pine-pitch arson confirmation, and a forged `#P7-088` **House Vesper** bond-slip with matching crimson wax from **Yard-Clerk Davin**. Leaving the Limestone Steps at `10:15`, Corin is intercepted at the Counting House Gate by both **Maren Vesper** and **Captain Kestrel**.
- **Central Pressure**: Break clear or leverage the double-house standoff before the midday Tide-Gate horn sounds at `12:00` (`elapsed_time_minutes: 345`, 105 minutes remaining).
- **Baseline Stakes**: Inspector Bren needs Corin's evidence back at Pier Seven to sustain seizure of *The Redwing*'s cargo; Maren Vesper aims to quiet or buy off the `#P7-088` forgery trail before the Port Reeve's writ arrives; Captain Kestrel wants to verify whether House Vesper torched a Merrow charter hull.
- **Zero Micro-Scene Rule**: Routine transit, fleeing down stairs, or preliminary parley yields `Delta: 0` XP. Award milestone XP (+15 to +25) only upon surviving/resolving the Counting House Gate standoff, cracking open the salt-crates to verify cargo truth, or confronting Tomas Vesper with documentary proof.

### Horizon II: The Estuarine Smuggling Ring (Turns 16–45)
- **Conditional Escalation**: Once the false bottom in the salt-crates is discovered (or if House Vesper successfully claims the crates unsearched), attention shifts upriver toward Ashwater Bend and the privateer rendezvous.
- **Faction Divergences**:
  - *If House Merrow is cornered on hull ownership*: Captain Kestrel offers Corin a dangerous truce—proof of who paid the arsonist in exchange for clearing Merrow's clean colliers.
  - *If House Vesper is pressed on the crimson wax die*: Maren Vesper uses her Port Reeve connections to threaten Corin's probation and calls in Tomas Vesper's debts as leverage.

### Horizon III: The Tide-Master's Ledger & Charter Reckoning (Turns 46–100)
- **Macro Stakes**: The black-powder smuggling ties into an illicit coastal blockade scheme backed by corrupt harbor signatories. Corin's choices decide whether Port Vane's Harbor Excise reclaims authority over the Outer Boom or bends to a house-brokered settlement.

---

## 2. Turn 6+ Conditional Faction Pressure Clocks

1. **If Corin demands written salvage claims at the Counting House Gate (Turn 6 Option 1)**:
   - Hold `narrative_intensity` at 3. Both Maren Vesper and Captain Kestrel stall with barbed counter-claims, advancing `tide_gate_audit` (`2 -> 3`) unless Corin forces Watch-Sergeant Orin or Inspector Bren's clerks into earshot.
2. **If Corin bolts down the Ferry Steps toward Pier Seven (Turn 6 Option 2)**:
   - Deduct `2C` ferry fare (`2G 12S 8C -> 2G 12S 6C`). Maren Vesper's guards give brief chase without crossing onto Excise planking; `house_interference` advances (`2 -> 3`), and Watch-Sergeant Orin notes the pursuit at the Pier Seven gate.
3. **If Corin trades pine-pitch arson proof to Captain Kestrel (Turn 6 Option 3)**:
   - House Merrow standing shifts from Hostile toward Opportunistic Ally; Captain Kestrel shoulders past Maren Vesper's guards, escalating House Merrow vs. House Vesper conflict (`house_interference` -> `3/6`, `Heat` +5) and putting House Vesper on immediate retaliation footing.
4. **If Corin bluffs Maren Vesper privately over `#P7-088` (Turn 6 Option 4)**:
   - Maren Vesper quietly checks whether Tomas Vesper leaked the pass serials (`MYSTERY-03` fuse lit). She may offer a sealed settlement or threaten Corin's probation; if Corin delays past `11:00`, advance `tide_gate_audit` (`2 -> 3`).
5. **If Corin or Inspector Bren pries open a crimson-stamped salt-crate at Pier Seven**:
   - Unlocks `MYSTERY-01` (black-powder kegs beneath coarse salt) and triggers an immediate Phase Milestone (+25 XP) plus Harbor Excise alarm before midday slack tide.

---

## 3. Hidden Canon Anchors (Refer to `WORLD_FOUNDATION/world_foundation.json`)

- **MYSTERY-01**: Beneath the coarse salt layer in the crimson-stamped crates sit waxed kegs of untaxed black powder. *(Still undiscovered by Corin at Turn 6.)*
- **MYSTERY-02**: *The Redwing*'s three-man crew was paid off and landed at Ashwater Bend before hired hands lit the wheelhouse with pine pitch. *(Partially corroborated at Turn 3 by Elena Reed's pitch test and Barge-Hand Pell's ferry sighting; full crew fate & employer still undiscovered.)*
- **MYSTERY-03**: Tomas Vesper signed two blank dock-passes to cover gambling markers at The Salt & Anchor; one cleared *The Redwing* upriver. *(Corin holds the `#P7-088` stub and forged bond-slip at Turn 6, but has not yet tied them to Tomas Vesper's debt.)*
