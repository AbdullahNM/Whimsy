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


if __name__ == "__main__":
    unittest.main()
