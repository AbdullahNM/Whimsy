#!/usr/bin/env python3
"""
Unit tests for campaign-agnostic pacing, progression enforcement, and grounding context assembly.
Tests:
- PromptAssembler loading campaign directives (AGENTS.md) and configuration
- StateParser parsing campaign-agnostic progression receipts (XP, PROGRESSION, DIVINITY, etc.)
- PacingController enforcing the Zero Micro-Scene Rule across zoom levels
"""

import os
import sys
import unittest
import tempfile
import json
import shutil

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.state_parser import StateParser
from ENGINE.pacing_controller import (
    PacingController,
    ZOOM_DETAILED_SCENE,
    ZOOM_SHORT_SUMMARY,
    ZOOM_MONTAGE,
    ZOOM_TIME_SKIP,
    SCENE_CONVERSATION,
    SCENE_TRAVEL,
    SCENE_CONFLICT,
    SCENE_DOWNTIME,
    SCENE_ROUTINE,
)
from ENGINE.prompt_assembler import PromptAssembler


class TestPacingProgressionGrounding(unittest.TestCase):
    def setUp(self):
        self.pacing = PacingController()

    def test_state_parser_generic_progression_resolutions(self):
        # 1. Standard XP
        text_xp = "[XP RESOLUTION: Previous: 100 | Delta: +10 (Practice) | New Total: 110 / 200]"
        res_xp = StateParser.parse_progression_resolution(text_xp)
        self.assertIsNotNone(res_xp)
        self.assertEqual(res_xp["delta"], 10)
        self.assertEqual(res_xp["current"], 110)
        self.assertEqual(res_xp["threshold"], 200)

        # 2. PROGRESSION/XP RESOLUTION
        text_dual = "[PROGRESSION/XP RESOLUTION: Previous: 75 | Delta: +6 (Holding Ground) | New Total: 81 / 100]"
        res_dual = StateParser.parse_progression_resolution(text_dual)
        self.assertIsNotNone(res_dual)
        self.assertEqual(res_dual["delta"], 6)
        self.assertEqual(res_dual["current"], 81)

        # 3. Campaign-specific: DIVINITY RESOLUTION (Cosmic Pantheon)
        text_div = "[DIVINITY RESOLUTION: Previous: 40 | Delta: +5 (Shrine Consecration) | New Total: 45 / 100]"
        res_div = StateParser.parse_progression_resolution(text_div)
        self.assertIsNotNone(res_div)
        self.assertEqual(res_div["delta"], 5)
        self.assertEqual(res_div["current"], 45)

        # 4. Campaign-specific: REALM RESOLUTION (without threshold)
        text_realm = "[REALM RESOLUTION: Previous: 120 | Delta: -10 (Wall Repair) | New Total: 110]"
        res_realm = StateParser.parse_progression_resolution(text_realm)
        self.assertIsNotNone(res_realm)
        self.assertEqual(res_realm["delta"], -10)
        self.assertEqual(res_realm["current"], 110)
        self.assertIsNone(res_realm["threshold"])

    def test_zero_micro_scene_rule_enforcement(self):
        # Conversation scene with +10 delta -> must be rejected (Zero Micro-Scene Rule)
        is_valid, msg = self.pacing.validate_progression_pacing(
            zoom_level=ZOOM_DETAILED_SCENE,
            scene_type=SCENE_CONVERSATION,
            delta=10,
            is_milestone=False,
            is_cycle_end=False
        )
        self.assertFalse(is_valid)
        self.assertIn("Zero Micro-Scene Rule", msg)

        # Conversation scene with 0 delta -> must be approved
        is_valid_zero, _ = self.pacing.validate_progression_pacing(
            zoom_level=ZOOM_DETAILED_SCENE,
            scene_type=SCENE_CONVERSATION,
            delta=0
        )
        self.assertTrue(is_valid_zero)

        # Routine travel scene with +15 delta -> rejected
        is_valid_travel, msg_travel = self.pacing.validate_progression_pacing(
            zoom_level=ZOOM_SHORT_SUMMARY,
            scene_type=SCENE_TRAVEL,
            delta=15
        )
        self.assertFalse(is_valid_travel)
        self.assertIn("Zero Micro-Scene Rule", msg_travel)

        # Montage zoom level with +25 delta -> approved
        is_valid_montage, _ = self.pacing.validate_progression_pacing(
            zoom_level=ZOOM_MONTAGE,
            scene_type=SCENE_ROUTINE,
            delta=25
        )
        self.assertTrue(is_valid_montage)

        # Daily cycle closure (is_cycle_end=True) in downtime -> approved
        is_valid_cycle, _ = self.pacing.validate_progression_pacing(
            zoom_level=ZOOM_DETAILED_SCENE,
            scene_type=SCENE_DOWNTIME,
            delta=5,
            is_cycle_end=True
        )
        self.assertTrue(is_valid_cycle)

        # Tournament milestone (is_milestone=True) in conflict -> approved
        is_valid_milestone, _ = self.pacing.validate_progression_pacing(
            zoom_level=ZOOM_DETAILED_SCENE,
            scene_type=SCENE_CONFLICT,
            delta=7,
            is_milestone=True
        )
        self.assertTrue(is_valid_milestone)

    def test_recommend_progression_envelope(self):
        env_routine = self.pacing.recommend_progression_envelope(
            zoom_level=ZOOM_DETAILED_SCENE,
            scene_type=SCENE_CONVERSATION
        )
        self.assertFalse(env_routine["allowed"])
        self.assertEqual(env_routine["recommended_delta_type"], "zero_delta")

        env_montage = self.pacing.recommend_progression_envelope(
            zoom_level=ZOOM_MONTAGE,
            scene_type=SCENE_ROUTINE
        )
        self.assertTrue(env_montage["allowed"])
        self.assertEqual(env_montage["recommended_delta_type"], "montage_macro")

    def test_prompt_assembler_loads_campaign_directives(self):
        # Create a mock campaign directory with AGENTS.md and campaign_config.json
        tmp_dir = tempfile.mkdtemp()
        try:
            camp_dir = os.path.join(tmp_dir, "CAMPAIGNS", "test_campaign")
            os.makedirs(camp_dir)

            agents_content = "# TEST CAMPAIGN AGENTS\nSetting: Cyber-Noir\nVocabulary: rain, neon, asphalt."
            with open(os.path.join(camp_dir, "AGENTS.md"), "w", encoding="utf-8") as f:
                f.write(agents_content)

            config_content = {"id": "test_campaign", "genre": "Cyber-Noir", "metrics": [{"id": "clues"}]}
            with open(os.path.join(camp_dir, "campaign_config.json"), "w", encoding="utf-8") as f:
                json.dump(config_content, f)

            assembler = PromptAssembler(tmp_dir)
            directives = assembler.load_campaign_agents_directives("test_campaign")
            self.assertIn("Cyber-Noir", directives)
            self.assertIn("Vocabulary: rain, neon, asphalt", directives)

            config = assembler.load_campaign_config("test_campaign")
            self.assertIn("test_campaign", config)
            self.assertIn("clues", config)

            # Test inclusion in build_system_prompt
            prompt = assembler.build_system_prompt("test_campaign")
            self.assertIn("# 2.1 CAMPAIGN-SPECIFIC DIRECTIVES & PROGRESSION DOCTRINE", prompt)
            self.assertIn("# 2.2 CAMPAIGN METRICS & CONFIGURATION", prompt)
        finally:
            shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    unittest.main()
