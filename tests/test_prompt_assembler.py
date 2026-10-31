#!/usr/bin/env python3
"""
Unit tests for ENGINE/prompt_assembler.py
Tests assembly of global rules, active turns, gameplay state, ideas, ontology, and context budgets.
"""

import os
import sys
import unittest
import tempfile
import shutil

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.prompt_assembler import PromptAssembler, assemble_prompt
from ENGINE.turn_archiver import record_turn, MAX_ACTIVE_TURNS


class TestPromptAssembler(unittest.TestCase):
    def setUp(self):
        self.assembler = PromptAssembler(ROOT_DIR)

    def test_load_global_rules(self):
        rules = self.assembler.load_global_rules()
        self.assertIn("CORE-001_HARD_CONSTRAINTS.md", rules)
        self.assertIn("CORE-002_TURN_ARCHITECTURE.md", rules)
        self.assertIn("CORE-003_ANTI_DEGRADATION.md", rules)

    def test_load_campaign_gameplay(self):
        gameplay = self.assembler.load_campaign_gameplay("template_campaign")
        self.assertIn("GAMEPLAY: STATUS", gameplay)
        self.assertIn("GAMEPLAY: RELATIONS", gameplay)
        self.assertIn("GAMEPLAY: ITEMS", gameplay)
        self.assertIn("GAMEPLAY: UPCOMING_HOOKS", gameplay)

    def test_load_campaign_ideas(self):
        ideas = self.assembler.load_campaign_ideas("template_campaign")
        self.assertIn("STORY STEERING & IDEAS", ideas)
        self.assertIn("narrative_steering.md", ideas)

    def test_load_campaign_ontology(self):
        ontology = self.assembler.load_campaign_ontology("template_campaign")
        self.assertIn("ACTIVE CAMPAIGN ONTOLOGY", ontology)
        self.assertIn("DISAMBIGUATION RULES", ontology)
        self.assertIn("COHORTS", ontology)

    def test_load_campaign_ontology_missing(self):
        # Non-existent campaign or missing ontology returns empty string without crashing
        ontology = self.assembler.load_campaign_ontology("non_existent_campaign")
        self.assertEqual(ontology, "")

    def test_build_system_prompt_sections(self):
        prompt = self.assembler.build_system_prompt("template_campaign")
        self.assertIn("GLOBAL SYSTEM CONSTRAINTS", prompt)
        self.assertIn("ACTIVE CAMPAIGN GAMEPLAY & STATE", prompt)
        self.assertIn("WORLD BIBLE & RELEVANT LORE", prompt)
        self.assertIn("STORY STEERING & NARRATIVE SEEDS", prompt)

    def test_assemble_prompt_helper(self):
        prompt = assemble_prompt("template_campaign", ROOT_DIR)
        self.assertTrue(len(prompt) > 500)
        self.assertIn("Metro Core", prompt)

    def test_context_budget_selective_lore_categories(self):
        full_lore = self.assembler.load_world_bible("template_campaign")
        filtered_lore = self.assembler.load_world_bible("template_campaign", specific_categories=["CORE"])
        self.assertLess(len(filtered_lore), len(full_lore))
        self.assertIn("WORLD BIBLE [CORE]", filtered_lore)
        self.assertNotIn("WORLD BIBLE [PEOPLE]", filtered_lore)

    def test_active_turns_context_budget(self):
        # Create a mock campaign in a temporary directory to test rolling turn assembly
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "CAMPAIGNS", "test_campaign")
            os.makedirs(os.path.join(camp_dir, "TURNS", "ACTIVE"))
            os.makedirs(os.path.join(camp_dir, "GAMEPLAY"))
            os.makedirs(os.path.join(camp_dir, "IDEAS"))
            os.makedirs(os.path.join(temp_dir, "GLOBAL"))

            # Create mock core rules
            with open(os.path.join(temp_dir, "GLOBAL", "CORE-001_HARD_CONSTRAINTS.md"), "w") as f:
                f.write("# Mock Constraints")

            # Record 20 turns
            for i in range(1, 21):
                record_turn(camp_dir, i, f"Action {i}", f"Response {i}")

            temp_assembler = PromptAssembler(temp_dir)
            prompt = temp_assembler.build_system_prompt("test_campaign")

            # Active turns buffer should have at most MAX_ACTIVE_TURNS (15)
            self.assertIn("turn_0020.md", prompt)
            self.assertIn("turn_0006.md", prompt)
            # Turns 1 through 5 should have been archived and thus NOT present in active prompt
            self.assertNotIn("turn_0001.md", prompt)
            self.assertNotIn("turn_0005.md", prompt)


if __name__ == "__main__":
    unittest.main()
