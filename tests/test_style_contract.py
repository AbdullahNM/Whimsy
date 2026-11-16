#!/usr/bin/env python3
"""
Unit tests for ENGINE/style_contract.py
Tests prose style validation, anti-degradation linter, sentence length enforcement,
STEM/calculus jargon bans, decorative micro-SFX bans, narrator praise bans,
formulaic closings, forced cliffhangers, and campaign config loading.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.style_contract import StyleContractValidator


class TestStyleContractValidator(unittest.TestCase):
    def setUp(self):
        self.validator = StyleContractValidator()

    # --- 1. Compliant Clean Prose Tests ---

    def test_compliant_clean_prose_passes(self):
        prose = (
            "You set your pack down against the cold wall. "
            "The courtyard is quiet except for the distant clatter of pots in the mess hall. "
            "A cool breeze stirs the dead leaves across the flagstones."
        )
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertTrue(is_compliant)
        self.assertEqual(violations, [])
        self.assertEqual(score, 1.0)

    def test_compliant_prose_with_choices_and_sys_block(self):
        turn_text = (
            "You nod to the guard and step past the iron gate into the lower ward. "
            "A warm scent of baked bread drifts from the bakery on the corner.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Head to the bakery to purchase travel rations.\n"
            "2. Inquire at the watchtower about passage permits.\n"
            "3. Walk down toward the river docks.\n\n"
            "[SYS: Turn 2 | Energy: 95 / 100 | Stress: 10 / 100 | Checkpoints: 5/5]"
        )
        is_compliant, violations, score = self.validator.validate_prose(turn_text)
        self.assertTrue(is_compliant, f"Expected compliant but got violations: {violations}")
        self.assertEqual(violations, [])
        self.assertEqual(score, 1.0)

    # --- 2. Calculus and STEM Jargon Tests ---

    def test_reynolds_quotient_fails(self):
        prose = "The master explained how the Reynolds quotient governed the pressure of the arcane valve."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Reynolds quotient" in v for v in violations))
        self.assertLess(score, 1.0)

    def test_lambda_and_impedance_fail(self):
        prose = "He adjusted the lambda frequency to match the natural impedance of the conductor."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("lambda" in v for v in violations))
        self.assertTrue(any("impedance" in v for v in violations))

    def test_shunt_tolerance_and_second_order_terms_fail(self):
        prose = (
            "The channel exceeded its shunt tolerance when calculating the second-order terms of the flow."
        )
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("shunt tolerance" in v for v in violations))
        self.assertTrue(any("second-order terms" in v for v in violations))

    def test_other_stem_jargon_fails(self):
        jargon_samples = [
            ("telemetry", "The device recorded the flight telemetry accurately."),
            ("eigenvalues", "Finding the eigenvalues of the matrix was essential."),
            ("Navier-Stokes", "The fluid followed standard Navier-Stokes dynamics."),
            ("Hamiltonian", "The system Hamiltonian conserved total energy."),
            ("decay constants", "The decay constants of the catalyst accelerated."),
            ("failure domains", "The defensive wards formed distinct failure domains."),
            ("decimal score", "Your technique reached an 85.8 index of efficiency."),
            ("percentage harder", "You struck fifty percent harder than before."),
        ]
        for term, text in jargon_samples:
            comp, vios, _ = self.validator.validate_prose(text)
            self.assertFalse(comp, f"Expected '{term}' to fail validation")
            self.assertTrue(any("STEM/calculus jargon" in v for v in vios))

    # --- 3. Decorative Micro-SFX Tests ---

    def test_sparks_danced_on_fork_fails(self):
        prose = "As you ate breakfast in the common hall, sparks danced on the fork."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Decorative micro-SFX" in v for v in violations))
        self.assertTrue(any("sparks danced on the fork" in v for v in violations))

    def test_room_trembled_fails(self):
        prose = "He spoke quietly about his family, and the room trembled with each word."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Decorative micro-SFX" in v for v in violations))
        self.assertTrue(any("room trembled" in v for v in violations))

    def test_air_grew_heavy_with_unspoken_power_fails(self):
        prose = "Across the dining table, the air grew heavy with unspoken power as she passed the salt."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Decorative micro-SFX" in v for v in violations))
        self.assertTrue(any("air grew heavy with unspoken power" in v for v in violations))

    def test_glowing_knuckles_and_table_slam_fail(self):
        prose = "His knuckles glowed with energy as his fist slammed the table, shaking the flagstones."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Decorative micro-SFX" in v for v in violations))

    # --- 4. Narrator Praise & Editorializing Tests ---

    def test_with_breathtaking_prowess_fails(self):
        prose = "With breathtaking prowess, you parried the training wooden sword."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Narrator praise/editorializing" in v for v in violations))
        self.assertTrue(any("With breathtaking prowess" in v for v in violations))

    def test_like_a_true_prodigy_fails(self):
        prose = "Like a true prodigy, you absorbed the entire manuscript within an hour."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Narrator praise/editorializing" in v for v in violations))
        self.assertTrue(any("Like a true prodigy" in v for v in violations))

    def test_unbeknownst_to_them_fails(self):
        prose = "Unbeknownst to them, you had already hidden the key in your boot."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Narrator praise/editorializing" in v for v in violations))
        self.assertTrue(any("Unbeknownst to them" in v for v in violations))

    def test_editorial_praise_phrases_fail(self):
        phrases = [
            "Little did they know what awaited them around the bend.",
            "It was a testament to your genius that the lock yielded.",
            "You vaulted the parapet with flawless grace.",
            "In an awe-inspiring display, you broke the stone slab.",
        ]
        for p in phrases:
            comp, vios, _ = self.validator.validate_prose(p)
            self.assertFalse(comp, f"Expected '{p}' to trigger narrator praise violation")
            self.assertTrue(any("Narrator praise/editorializing" in v for v in vios))

    # --- 5. Formulaic Turn Closings Tests ---

    def test_the_choice_is_yours_fails(self):
        prose = "Two doors stand open before you in the damp tunnel. The choice is yours..."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Formulaic turn closing" in v for v in violations))
        self.assertTrue(any("The choice is yours" in v for v in violations))

    def test_what_will_you_do_fails(self):
        prose = "The patrol steps onto the bridge with torches drawn. What will you do?"
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Formulaic turn closing" in v for v in violations))
        self.assertTrue(any("What will you do" in v for v in violations))

    def test_other_formulaic_closings_fail(self):
        closings = [
            "The decision is yours.",
            "How will you proceed?",
            "What do you do?",
            "Where will your journey take you?",
        ]
        for c in closings:
            comp, vios, _ = self.validator.validate_prose(f"The path branches ahead. {c}")
            self.assertFalse(comp, f"Expected '{c}' to be flagged as formulaic closing")
            self.assertTrue(any("Formulaic turn closing" in v for v in vios))

    # --- 6. Forced Cliffhangers Tests ---

    def test_suddenly_everything_went_black_fails(self):
        prose = "You reached for the latch on the cabinet door. Suddenly, everything went black..."
        is_compliant, violations, score = self.validator.validate_prose(prose)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Forced cliffhanger" in v for v in violations))
        self.assertTrue(any("Suddenly, everything went black" in v for v in violations))

    def test_other_forced_cliffhangers_fail(self):
        cliffhangers = [
            "Just when you thought it was safe, the bell tolled.",
            "Before you could react, disaster struck the tavern.",
            "To be continued...",
            "Out of nowhere, an enemy appeared.",
        ]
        for ch in cliffhangers:
            comp, vios, _ = self.validator.validate_prose(ch)
            self.assertFalse(comp, f"Expected '{ch}' to fail forced cliffhanger check")
            self.assertTrue(any("Forced cliffhanger" in v for v in vios))

    # --- 7. Sentence Length Checks ---

    def test_max_sentence_length_flagged(self):
        # A 40-word run-on sentence exceeds the 35-word limit
        long_sentence = (
            "You cautiously step along the dark flagstones of the northern rampart while listening intently "
            "to the distant murmurs of the changing watch and watching the flicker of iron lanterns against "
            "the thick granite stones as the midnight drizzle begins to fall softly upon the parapet."
        )
        words = long_sentence.split()
        self.assertGreater(len(words), 35)

        is_compliant, violations, score = self.validator.validate_prose(long_sentence)
        self.assertFalse(is_compliant)
        self.assertTrue(any("exceeds max word limit" in v for v in violations))

    def test_average_sentence_length_flagged(self):
        # Two sentences with 32 words each: within 35 max, but avg 32 exceeds default 28
        s1 = (
            "The blacksmith hauled the glowing billet from the furnace hearth and laid it carefully across "
            "the cold anvil while his apprentice readied the heavy iron hammer for the first strike."
        )
        s2 = (
            "They worked in steady rhythmic turns under the smoky rafters of the forge until the orange "
            "metal gradually cooled into a dark red wedge ready for the oil quench."
        )
        text = f"{s1} {s2}"
        is_compliant, violations, score = self.validator.validate_prose(text)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Average sentence length" in v for v in violations))

    # --- 8. Config Overrides and Prohibited Patterns ---

    def test_config_disabling_stem_check(self):
        prose = "The Reynolds quotient was calibrated."
        # Enabled by default: fails
        comp_default, _, _ = self.validator.validate_prose(prose)
        self.assertFalse(comp_default)

        # Disabled by config override: passes
        comp_custom, vios_custom, _ = self.validator.validate_prose(
            prose, config={"ban_stem_calculus_jargon": False}
        )
        self.assertTrue(comp_custom, f"Expected pass when check disabled, got {vios_custom}")

    def test_custom_prohibited_patterns(self):
        prose = "He used a vortical edge infusion kata during practice."
        cfg = {"prohibited_patterns": [r"\bvortical\s+edge\s+infusion\b"]}
        comp, vios, _ = self.validator.validate_prose(prose, config=cfg)
        self.assertFalse(comp)
        self.assertTrue(any("Prohibited custom pattern" in v for v in vios))

    # --- 9. Direct Class Invocation and Loader ---

    def test_direct_class_validate_prose(self):
        comp, vios, score = StyleContractValidator.validate_prose("A clean simple turn.")
        self.assertTrue(comp)
        self.assertEqual(vios, [])
        self.assertEqual(score, 1.0)

        comp_bad, vios_bad, _ = StyleContractValidator.validate_prose("Check the impedance.")
        self.assertFalse(comp_bad)

    def test_class_validate_method(self):
        comp, vios, score = StyleContractValidator.validate("A clean simple turn.")
        self.assertTrue(comp)

    def test_from_campaign_loader(self):
        validator = StyleContractValidator.from_campaign("template_campaign", ROOT_DIR)
        self.assertEqual(validator.config.get("mode"), "natural_everyday_english")
        self.assertEqual(validator.config.get("max_sentence_words"), 35)
        self.assertTrue(validator.config.get("ban_stem_calculus_jargon"))

    # --- 10. Fourth-Wall Seal State Change Validation (R6) ---

    def test_uncontained_xp_receipt_fails_fourth_wall_seal(self):
        from ENGINE.outcome import Outcome
        outcome = Outcome(progression_delta={"energy": -5}, version=1)
        prose = (
            "You secure the perimeter latch with a firm turn.\n\n"
            "[XP RESOLUTION: Previous: 100 | Delta: +50 (Combat) | New Total: 150 / 200]"
        )
        is_compliant, vios, score = self.validator.validate_prose(prose, outcome=outcome)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Fourth-wall seal violation" in v for v in vios))
        self.assertTrue(any("progression delta (50) not contained in outcome" in v for v in vios))

    def test_matching_xp_receipt_passes_fourth_wall_seal(self):
        from ENGINE.outcome import Outcome
        outcome = Outcome(progression_delta={"xp": 50}, version=1)
        prose = (
            "You secure the perimeter latch with a firm turn.\n\n"
            "[XP RESOLUTION: Previous: 100 | Delta: +50 (Combat) | New Total: 150 / 200]"
        )
        is_compliant, vios, score = self.validator.validate_prose(prose, outcome=outcome)
        self.assertTrue(is_compliant, f"Expected compliant but got violations: {vios}")

    def test_uncontained_diegetic_stat_assertion_fails_fourth_wall_seal(self):
        from ENGINE.outcome import Outcome
        outcome = Outcome(progression_delta={}, resources_delta={}, version=1)
        prose = "You defeated the intruder and earned 500 gold for your valiant efforts."
        is_compliant, vios, score = self.validator.validate_prose(prose, outcome=outcome)
        self.assertFalse(is_compliant)
        self.assertTrue(any("Fourth-wall seal violation" in v for v in vios))
        self.assertTrue(any("currency gain (500) not contained in outcome" in v for v in vios))

    # --- 11. Issue #30: Expanded Synonym Permutations & Heuristic Tests ---

    def test_stem_jargon_synonym_variations_fail(self):
        variations = [
            ("exponent of talent", "His exponent of talent was recognized by everyone in the guild."),
            ("quantum", "The relic triggered a sudden quantum fluctuation in the stone chamber."),
            ("deceleration multiplier", "The device activated its deceleration multiplier to halt the wheel."),
            ("acceleration multiplier", "An acceleration multiplier propelled the projectile forward."),
        ]
        for term, prose in variations:
            comp, vios, _ = self.validator.validate_prose(prose)
            self.assertFalse(comp, f"Expected STEM jargon '{term}' to fail validation")
            self.assertTrue(
                any("Prohibited STEM/calculus jargon" in v for v in vios),
                f"Expected jargon violation for '{term}', got: {vios}"
            )

    def test_narrator_praise_synonym_bypasses_fail(self):
        bypasses = [
            ("peerless genius", "He proved himself a peerless genius when deciphering the cryptic glyphs."),
            ("display was unmatched", "Her swordsmanship display was unmatched in the entire grand pavilion."),
            ("exhibition of brilliance", "It was an exhibition of brilliance from the untested recruit."),
            ("masterclass in", "The commander delivered a masterclass in defensive coordination."),
            ("superhuman feat", "He performed a superhuman feat by holding the falling iron portcullis."),
            ("unrivaled precision", "With unrivaled precision, the scout severed the signal cord."),
            ("unrivaled precision (standalone)", "Her unrivaled precision left the veteran archers stunned."),
        ]
        for phrase, prose in bypasses:
            comp, vios, _ = self.validator.validate_prose(prose)
            self.assertFalse(comp, f"Expected narrator praise '{phrase}' to fail validation")
            self.assertTrue(
                any("Narrator praise/editorializing" in v for v in vios),
                f"Expected narrator praise violation for '{phrase}', got: {vios}"
            )

    def test_tableware_and_cutlery_micro_sfx_synonyms_fail(self):
        cutlery_cases = [
            ("sparks on spoon", "As he drank the warm broth, sparks danced on the spoon."),
            ("static across bowl", "She paused mid-sentence, static across bowl catching her eye."),
            ("static danced across bowl", "Static danced across the bowl as the tea was served."),
            ("sparks on fork", "While enjoying breakfast, sparks danced on the fork."),
            ("arcs crackled along table", "Arcs crackled along the table as the envoys sat down."),
            ("embers leaped from goblet", "Embers leaped from her goblet into the empty trencher."),
            ("currents jumped across cutlery", "Currents jumped across the cutlery set beside the plate."),
            ("energy sparking off mug", "Blue energy sparking off his mug startled the innkeeper."),
        ]
        for desc, prose in cutlery_cases:
            comp, vios, _ = self.validator.validate_prose(prose)
            self.assertFalse(comp, f"Expected micro-SFX '{desc}' to fail validation")
            self.assertTrue(
                any("Decorative micro-SFX" in v for v in vios),
                f"Expected micro-SFX violation for '{desc}', got: {vios}"
            )

    # --- 12. Issue #30: Scene-Context Awareness & Gating Tests ---

    def test_scene_context_gating_blade_clash_in_combat_passes(self):
        blade_clash_prose = (
            "The bandit lunged with a heavy cut, but your blade clashed against his iron armor, "
            "sparks dancing from the impact as you turned the blow aside."
        )
        combat_scenes = ["combat", "duel", "clash", "tactical"]
        for st in combat_scenes:
            is_compliant, vios, score = self.validator.validate_prose(
                blade_clash_prose, scene_type=st
            )
            self.assertTrue(
                is_compliant,
                f"Expected blade clash sparks to pass in scene_type='{st}', got violations: {vios}"
            )
            self.assertEqual(vios, [])
            self.assertEqual(score, 1.0)

    def test_scene_context_gating_blade_clash_in_downtime_fails(self):
        blade_clash_prose = (
            "The bandit lunged with a heavy cut, but your blade clashed against his iron armor, "
            "sparks dancing from the impact as you turned the blow aside."
        )
        downtime_scenes = ["downtime", "transit", "conversation", "routine", "exploration", "mundane"]
        for st in downtime_scenes:
            is_compliant, vios, _ = self.validator.validate_prose(
                blade_clash_prose, scene_type=st
            )
            self.assertFalse(
                is_compliant,
                f"Expected blade clash sparks to be rejected in scene_type='{st}'"
            )
            self.assertTrue(any("Decorative micro-SFX" in v for v in vios))

        # Unspecified scene_type defaults to zero-tolerance
        is_compliant, vios, _ = self.validator.validate_prose(blade_clash_prose, scene_type=None)
        self.assertFalse(is_compliant, "Expected blade clash sparks to fail when scene_type is unspecified")
        self.assertTrue(any("Decorative micro-SFX" in v for v in vios))

    def test_cutlery_sparks_fail_in_both_combat_and_downtime(self):
        prose_spoon = "During the heated confrontation, sparks danced on the spoon beside the hearth."
        prose_fork = "In the thick of the fray, sparks danced on the fork on the tavern counter."
        prose_bowl = "As the enemies clashed, static danced across the bowl on the shelf."

        test_sentences = [prose_spoon, prose_fork, prose_bowl]
        scene_types_to_test = ["combat", "duel", "clash", "downtime", "conversation", "transit", None]

        for st in scene_types_to_test:
            for prose in test_sentences:
                is_compliant, vios, _ = self.validator.validate_prose(prose, scene_type=st)
                self.assertFalse(
                    is_compliant,
                    f"Expected cutlery micro-SFX to fail in scene_type='{st}' for prose: '{prose}'"
                )
                self.assertTrue(
                    any("Decorative micro-SFX" in v for v in vios),
                    f"Expected micro-SFX violation in scene_type='{st}', got: {vios}"
                )

    def test_scene_context_resolved_from_outcome_next_state(self):
        from ENGINE.outcome import Outcome

        blade_clash_prose = (
            "Your steel blade clashed against the shield, sparks dancing as you deflected the strike."
        )

        combat_outcome = Outcome(
            next_state={"pacing_state": {"scene_type": "combat"}},
            version=1
        )
        is_comp, vios, score = self.validator.validate_prose(blade_clash_prose, outcome=combat_outcome)
        self.assertTrue(is_comp, f"Expected combat outcome to permit blade clash sparks, got: {vios}")
        self.assertEqual(score, 1.0)

        downtime_outcome = Outcome(
            next_state={"pacing_state": {"scene_type": "downtime"}},
            version=1
        )
        is_comp, vios, _ = self.validator.validate_prose(blade_clash_prose, outcome=downtime_outcome)
        self.assertFalse(is_comp, "Expected downtime outcome to reject blade clash sparks")
        self.assertTrue(any("Decorative micro-SFX" in v for v in vios))

    def test_scene_context_resolved_from_outcome_metadata(self):
        from ENGINE.outcome import Outcome

        blade_clash_prose = (
            "Your steel blade clashed against the shield, sparks dancing as you deflected the strike."
        )

        outcome_combat_meta = Outcome(version=1)
        outcome_combat_meta.metadata = {"scene_type": "combat"}
        is_comp, vios, score = self.validator.validate_prose(blade_clash_prose, outcome=outcome_combat_meta)
        self.assertTrue(is_comp, f"Expected combat metadata to permit blade clash sparks, got: {vios}")
        self.assertEqual(score, 1.0)

        outcome_downtime_meta = Outcome(version=1)
        outcome_downtime_meta.metadata = {"scene_type": "conversation"}
        is_comp, vios, _ = self.validator.validate_prose(blade_clash_prose, outcome=outcome_downtime_meta)
        self.assertFalse(is_comp, "Expected conversation metadata to reject blade clash sparks")
        self.assertTrue(any("Decorative micro-SFX" in v for v in vios))


if __name__ == "__main__":
    unittest.main()
