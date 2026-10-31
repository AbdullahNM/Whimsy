#!/usr/bin/env python3
"""
Unit tests for ENGINE/state_parser.py
Tests parsing of [XP RESOLUTION: ...], [CURRENCY RESOLUTION: ...], [SYS: ...],
markdown state updates, and JSON arithmetic boundary validations.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.state_parser import StateParser


class TestStateParser(unittest.TestCase):
    def test_parse_xp_resolution_standard(self):
        text = "The spar concludes with applause. [XP RESOLUTION: Previous: 315 | Delta: +15 (Tactical Sparring) | New Total: 330 / 500]"
        result = StateParser.parse_xp_resolution(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["previous"], 315)
        self.assertEqual(result["delta"], 15)
        self.assertEqual(result["reason"], "Tactical Sparring")
        self.assertEqual(result["current"], 330)
        self.assertEqual(result["threshold"], 500)

    def test_parse_xp_resolution_negative_delta(self):
        text = "[XP RESOLUTION: Previous: 100 | Delta: -10 (Fatigue penalty) | New Total: 90 / 500]"
        result = StateParser.parse_xp_resolution(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["previous"], 100)
        self.assertEqual(result["delta"], -10)
        self.assertEqual(result["current"], 90)

    def test_parse_xp_resolution_fallback(self):
        text = "Outcome note: [XP RESOLUTION: Arbitrary commentary here | New Total: 450 / 500]"
        result = StateParser.parse_xp_resolution(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["current"], 450)
        self.assertEqual(result["threshold"], 500)

    def test_parse_xp_resolution_missing(self):
        text = "There is no xp resolution block in this text."
        self.assertIsNone(StateParser.parse_xp_resolution(text))

    def test_parse_currency_resolution_standard(self):
        text = "You paid for supplies. [CURRENCY RESOLUTION: Previous: 3G 6S 20C | Delta: -1G 2S (Reagents) | New Purse: 2G 4S 20C]"
        result = StateParser.parse_currency_resolution(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["previous"], "3G 6S 20C")
        self.assertEqual(result["delta"], "-1G 2S (Reagents)")
        self.assertEqual(result["new_purse"], "2G 4S 20C")

    def test_parse_currency_resolution_fallback(self):
        text = "Receipt: [CURRENCY RESOLUTION: Total calculation | New Purse: 10G 0S 0C]"
        result = StateParser.parse_currency_resolution(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["new_purse"], "10G 0S 0C")

    def test_parse_currency_resolution_missing(self):
        text = "No coins exchanged hands."
        self.assertIsNone(StateParser.parse_currency_resolution(text))

    def test_parse_system_block(self):
        text = "Scene ended. [SYS: Turn 246 | Lvl 3 Initiate Peak | XP 330/500 | Purse: 3G 6S 20C | Strain 2/10 | Checkpoints: 5/5]"
        result = StateParser.parse_system_block(text)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("turn"), 246)
        self.assertEqual(result.get("level"), 3)
        self.assertEqual(result.get("strain"), "2/10")

    def test_parse_system_block_missing(self):
        text = "Just a standard narrative response."
        self.assertIsNone(StateParser.parse_system_block(text))

    def test_apply_state_mutations_markdown(self):
        gm_text = (
            "Good spar.\n"
            "[XP RESOLUTION: Previous: 315 | Delta: +15 (Sparring) | New Total: 330 / 500]\n"
            "[CURRENCY RESOLUTION: Previous: 3G 6S 20C | Delta: 0 | New Purse: 4G 0S 0C]\n"
            "[SYS: Turn 246 | Lvl 3 | Strain 3/10]"
        )
        sample_status_md = "# Status\n- **XP**: 315 / 500\n- **Strain**: 0/10\n"
        sample_items_md = "# Inventory\n- **Current Coin**: `3G 6S 20C`\n"

        new_status, new_items, modified = StateParser.apply_state_mutations(gm_text, sample_status_md, sample_items_md)
        self.assertTrue(modified)
        self.assertIn("330 / 500", new_status)
        self.assertIn("3/10", new_status)
        self.assertIn("`4G 0S 0C`", new_items)

    def test_apply_state_mutations_json(self):
        gm_text = (
            "Contract completed successfully!\n"
            "[XP RESOLUTION: Previous: 315 | Delta: +35 (Contract Completion) | New Total: 350 / 500]\n"
            "[CURRENCY RESOLUTION: Previous: 3G 6S 20C | Delta: +2G | New Purse: 5G 6S 20C]\n"
            "[SYS: Turn 246 | Lvl 3 | Strain 4/10]"
        )
        status_json = {
            "campaign_id": "template_campaign",
            "turn": 245,
            "progression": {
                "level": 3,
                "xp": 315,
                "xp_threshold": 500,
                "mana_strain": 0,
                "strain_max": 10
            },
            "purse": {
                "gold": 3,
                "silver": 6,
                "copper": 20,
                "display": "3G 6S 20C"
            }
        }

        updated_json, modified = StateParser.apply_state_mutations_json(gm_text, status_json)
        self.assertTrue(modified)
        self.assertEqual(updated_json["turn"], 246)
        self.assertEqual(updated_json["progression"]["xp"], 350)
        self.assertEqual(updated_json["progression"]["mana_strain"], 4)
        self.assertEqual(updated_json["purse"]["display"], "5G 6S 20C")
        self.assertEqual(updated_json["purse"]["gold"], 5)
        self.assertEqual(updated_json["purse"]["silver"], 6)
        self.assertEqual(updated_json["purse"]["copper"], 20)

        # Original dict should not have been mutated (deepcopy safety)
        self.assertEqual(status_json["turn"], 245)
        self.assertEqual(status_json["progression"]["xp"], 315)

    def test_arithmetic_boundaries_xp_progression(self):
        # Test boundary where XP exceeds threshold
        gm_text = "[XP RESOLUTION: Previous: 490 | Delta: +20 (Crucible) | New Total: 510 / 500]"
        status_json = {
            "progression": {"xp": 490, "xp_threshold": 500}
        }
        updated_json, modified = StateParser.apply_state_mutations_json(gm_text, status_json)
        self.assertTrue(modified)
        self.assertEqual(updated_json["progression"]["xp"], 510)
        self.assertGreaterEqual(updated_json["progression"]["xp"], updated_json["progression"]["xp_threshold"])

    def test_dynamic_strain_and_credits_mutation(self):
        gm_text = (
            "[XP RESOLUTION: Previous: 40 | Delta: +0 (Lecture) | New Total: 40 / 100]\n"
            "[CURRENCY RESOLUTION: Previous: 300 ₡ | Delta: +50 | New Purse: 350 ₡]\n"
            "[SYS: Turn 21 | Tier 1 Iron Initiate | XP 40/100 | Purse: 350 ₡ | Strain 5/100 | Checkpoints: 5/5]"
        )
        status_json = {
            "turn": 20,
            "progression": {
                "xp": 40,
                "xp_threshold": 100,
                "ocular_strain": 3,
                "strain_max": 100
            },
            "purse": {
                "credits": 300,
                "display": "300 ₡"
            }
        }
        updated_json, modified = StateParser.apply_state_mutations_json(gm_text, status_json)
        self.assertTrue(modified)
        self.assertEqual(updated_json["turn"], 21)
        self.assertEqual(updated_json["progression"]["ocular_strain"], 5)
        self.assertNotIn("mana_strain", updated_json["progression"])
        self.assertEqual(updated_json["purse"]["credits"], 350)
        self.assertEqual(updated_json["purse"]["display"], "350 ₡")


if __name__ == "__main__":
    unittest.main()
