# CAMPAIGN DIRECTIVES — THE CINDER LEDGER (`sample_campaign`)

> **Campaign Authority**: These directives govern all gameplay turns, pacing, progression, and tone for *The Cinder Ledger*. They operate under the global codices (`GLOBAL/CORE-001` through `CORE-003`).

---

## 1. Setting Register & Vocabulary Rules

* **Genre**: Low-Fantasy Maritime Intrigue & Guild Mystery.
* **Setting**: **Port Vane**, a rain-slicked tidal city built on black slate pilings and limestone sea-walls at the mouth of the Ashwater estuary.
* **Grounded Material Register**:
  * Use tactile maritime and excise vocabulary: *oilskin, tarred hemp, slate pilings, iron harbor chains, tide-gates, brass seal-punches, tallow lanterns, salt-crates, wax stamps, tally-sticks, colliers, packet boats*.
  * **Zero High-Magic / Modern-Tech Bleed**: No fireballs, glowing runes, mana pools, firearms, or modern corporate/STEM terminology. Alchemy in Port Vane is limited to mundane apothecary mixtures, pitch, lantern oils, and shipwright preservatives.
* **Tone & Style Contract**:
  * Plain, everyday English (`max_sentence_words: 35`).
  * Keep dialogue grounded in dockside practicality, ledger disputes, and quiet political pressure.
  * Never include decorative micro-SFX, narrator praise, forced cliffhangers, or formulaic closing questions.

---

## 2. Protagonist Profile

* **Name**: Corin Hale
* **Title**: Junior Harbor Excise Clerk & Field Auditor
* **Origin**: Lower Quay
* **Status**: On Probation
* **Faction**: Harbor Excise Office
* **Starting Purse**: `2G 14S 8C`
* **Operational Footing**: Corin carries a brass excise seal-punch, a damp oilskin coat, and an oiled leather ledger satchel. He knows the docks, tides, and freight marks better than the high counting houses, and he is one serious mistake away from dismissal.

---

## 3. Mandatory Entity Disambiguation Rules

Agents must strictly enforce the disambiguation rules recorded in `ontology.json`:

1. **Maren Vesper vs. Tomas Vesper (`VESPER-01`)**:
   * **Maren Vesper** (`maren_vesper`) is the Factor-General of House Vesper—wealthy, older, sharp-tongued, operating from the Limestone Steps counting house.
   * **Tomas Vesper** (`tomas_vesper`) is a junior watch-clerk at Pier Seven Customs Shed and Maren's estranged nephew—nervous, debt-ridden, and employed under Inspector Bren.
   * **Rule**: Never write a lone surname ("Vesper") in narration or dialogue where either could be meant. Always specify **Maren Vesper** (or Factor-General Vesper) vs. **Tomas Vesper**.
2. **Captain Orlov vs. Watch-Sergeant Orin (`ORIN-ORLOV-01`)**:
   * **Captain Orlov** (`captain_orlov`) commands the harbor excise cutter *Grey Gull* on the outer estuary patrol.
   * **Watch-Sergeant Orin** (`watch_sergeant_orin`) commands the Outer Boom gatehouse watch on the pier wall.
   * **Rule**: Never merge or confuse the two names or postings.

---

## 4. Progression, Clocks & Currency Rules

### A. Zero Micro-Scene Rule & Milestone Progression
* **Routine Turns (`Delta: 0`)**: Ordinary dockside walking, tavern talk, routine manifest sorting, and resting award strictly `Delta: 0` progression (`[PROGRESSION/XP RESOLUTION: Previous: X | Delta: 0 (...) | New Total: X / 100]`).
* **Audit & Investigation Milestones**: Progression increments (+15 to +25 XP) occur only when Corin completes a major audit phase, secures verified primary evidence before a deadline, or survives a formal house confrontation.
* **Clocks**:
  * **Midday Tide-Gate Audit (`tide_gate_audit`, 0/4, known)**: Advances when time passes without clearing or impounding *The Redwing*'s cargo, or when delays eat into the morning watch.
  * **House Interference (`house_interference`, 0/6, suspected)**: Advances when House Merrow or House Vesper catches wind of Corin's inquiries or when Heat rises through loud dockside confrontations.

### B. Currency Denominations
* **Gold Crowns (`G`)**: 1 Gold Crown = 20 Silver Marks (`S`).
* **Silver Marks (`S`)**: 1 Silver Mark = 12 Copper Pence (`C`).
* **Copper Pence (`C`)**: Everyday dockside coin for ferries, ink, tea, and porter tips.
* Display format in receipts and `status.json`: `<G>G <S>S <C>C` (e.g., `2G 14S 8C`).

---

## 5. Epistemic Separation & Read-Only Lore Mandate

* **Active GM (`cyoa-gm`)**: Must treat `WORLD_BIBLE/` and `ontology.json` as **strictly read-only**. Log incidental dockworkers, barkeeps, and watchmen under `transient_contacts` in `GAMEPLAY/relations.json` and `GAMEPLAY/relations.md`.
* **No Canon Leaks**: Secrets stored in `WORLD_FOUNDATION/world_foundation.json` (`unresolved_mysteries`) and `IDEAS/narrative_steering.md` must never appear in `GAMEPLAY/` files or unearned NPC dialogue.
