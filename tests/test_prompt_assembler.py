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
import json

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

    def test_section_budget_config_loading(self):
        """Verifies loading of token_budget and char_budget with default fallbacks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "CAMPAIGNS", "budget_camp")
            os.makedirs(camp_dir)

            # 1. token_budget block with partial override
            cfg_data = {
                "id": "budget_camp",
                "token_budget": {
                    "rules_char_budget": 5000,
                    "active_turns_budget": 3
                }
            }
            with open(os.path.join(camp_dir, "campaign_config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg_data, f)

            assembler = PromptAssembler(temp_dir)
            budget = assembler.get_campaign_budget_config("budget_camp")
            self.assertEqual(budget["rules_char_budget"], 5000)
            self.assertEqual(budget["active_turns_budget"], 3)
            # Default fallbacks
            self.assertEqual(budget["world_foundation_char_budget"], PromptAssembler.DEFAULT_WORLD_FOUNDATION_CHAR_BUDGET)
            self.assertEqual(budget["ideas_char_budget"], PromptAssembler.DEFAULT_IDEAS_CHAR_BUDGET)

            # 2. char_budget alias block
            cfg_data_alt = {
                "id": "budget_camp",
                "char_budget": {
                    "world_foundation_char_budget": 3500
                }
            }
            with open(os.path.join(camp_dir, "campaign_config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg_data_alt, f)

            budget_alt = assembler.get_campaign_budget_config("budget_camp")
            self.assertEqual(budget_alt["world_foundation_char_budget"], 3500)
            self.assertEqual(budget_alt["rules_char_budget"], PromptAssembler.DEFAULT_RULES_CHAR_BUDGET)
            self.assertEqual(budget_alt["active_turns_budget"], PromptAssembler.DEFAULT_ACTIVE_TURNS_BUDGET)

    def test_section_budget_rules_truncation(self):
        """Verifies rules are clamped within rules_char_budget."""
        full_rules = self.assembler.load_global_rules()
        self.assertGreater(len(full_rules), 20000)

        # Truncate to 1200 characters
        budgeted_rules = self.assembler.load_global_rules(max_chars=1200)
        self.assertLessEqual(len(budgeted_rules), 1200)
        self.assertIn("TRUNCATED DUE TO RULES BUDGET", budgeted_rules)
        self.assertIn("CORE-001_HARD_CONSTRAINTS.md", budgeted_rules)

    def test_section_budget_ideas_truncation(self):
        """Verifies ideas are clamped within ideas_char_budget."""
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "CAMPAIGNS", "ideas_camp")
            ideas_dir = os.path.join(camp_dir, "IDEAS")
            os.makedirs(ideas_dir)

            with open(os.path.join(ideas_dir, "long_idea.md"), "w", encoding="utf-8") as f:
                f.write("A" * 5000)

            assembler = PromptAssembler(temp_dir)
            full_ideas = assembler.load_campaign_ideas("ideas_camp")
            self.assertGreaterEqual(len(full_ideas), 5000)

            budgeted_ideas = assembler.load_campaign_ideas("ideas_camp", max_chars=800)
            self.assertLessEqual(len(budgeted_ideas), 800)
            self.assertIn("TRUNCATED DUE TO IDEAS BUDGET", budgeted_ideas)

    def test_section_budget_active_turns(self):
        """Verifies active_turns_budget limits turns in assembled prompt."""
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "CAMPAIGNS", "turns_camp")
            os.makedirs(os.path.join(camp_dir, "TURNS", "ACTIVE"))
            os.makedirs(os.path.join(camp_dir, "GAMEPLAY"))
            os.makedirs(os.path.join(camp_dir, "IDEAS"))
            os.makedirs(os.path.join(temp_dir, "GLOBAL"))

            with open(os.path.join(temp_dir, "GLOBAL", "CORE-001_HARD_CONSTRAINTS.md"), "w") as f:
                f.write("# Mock Constraints")

            # Config with active_turns_budget = 3
            cfg = {
                "id": "turns_camp",
                "token_budget": {
                    "active_turns_budget": 3
                }
            }
            with open(os.path.join(camp_dir, "campaign_config.json"), "w", encoding="utf-8") as f:
                json.dump(cfg, f)

            # Record 8 turns
            for i in range(1, 9):
                record_turn(camp_dir, i, f"Action {i}", f"Response {i}")

            assembler = PromptAssembler(temp_dir)
            prompt = assembler.build_system_prompt("turns_camp")

            # Only turns 6, 7, 8 should be present
            self.assertIn("turn_0008.md", prompt)
            self.assertIn("turn_0007.md", prompt)
            self.assertIn("turn_0006.md", prompt)
            self.assertNotIn("turn_0005.md", prompt)
            self.assertNotIn("turn_0004.md", prompt)
            self.assertNotIn("turn_0001.md", prompt)

    def test_section_budget_world_foundation_clamping(self):
        """Verifies world foundation is clamped within world_foundation_char_budget."""
        full_wf = self.assembler.load_world_foundation("template_campaign")
        self.assertGreater(len(full_wf), 3000)

        budgeted_wf = self.assembler.load_world_foundation("template_campaign", max_chars=900)
        self.assertLessEqual(len(budgeted_wf), 900)
        self.assertIn("TRUNCATED DUE TO WORLD FOUNDATION BUDGET", budgeted_wf)
        self.assertIn("IMMUTABLE FACTS", budgeted_wf)

    def test_progressive_disclosure_filtering_by_scene_anchor(self):
        """Verifies progressive disclosure filters factions, NPCs, and rumors to relevant scene anchor."""
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "CAMPAIGNS", "sandbox_camp")
            wf_dir = os.path.join(camp_dir, "WORLD_FOUNDATION")
            os.makedirs(wf_dir)

            wf_data = {
                "campaign_id": "sandbox_camp",
                "schema_version": "1.0.0",
                "immutable_facts": [
                    {"id": "FACT-01", "category": "geography", "statement": "Atmosphere requires station reactors."}
                ],
                "mutable_world_state": {
                    "active_epoch": "Solar Reconstruction",
                    "factions_control": {"Station Security": "Central Spire"}
                },
                "factions_and_tensions": [
                    {
                        "id": "terminal_security",
                        "name": "Terminal Bay Security",
                        "agenda": "Enforce cargo manifest inspection at Terminal Bay A.",
                        "objectives": ["Inspect all freight containers in Terminal Bay"],
                        "tensions": [{"target_entity": "Smugglers", "source_of_friction": "Illegal contraband"}]
                    },
                    {
                        "id": "asteroid_miners",
                        "name": "Deep Asteroid 9 Miners",
                        "agenda": "Extract crystalline ores from outer Asteroid 9 belt.",
                        "objectives": ["Defend deep asteroid drilling rigs"],
                        "tensions": [{"target_entity": "Cartel", "source_of_friction": "Claim jumping"}]
                    }
                ],
                "npc_knowledge": {
                    "officer_chen": {
                        "knows": ["Cargo manifests for Terminal Bay A", "Terminal Bay security codes"],
                        "does_not_know": ["Smuggler identities"],
                        "falsely_believes": ["All bay cameras are operational"]
                    },
                    "miner_jax": {
                        "knows": ["Asteroid 9 shaft depths", "Drill engine repair"],
                        "does_not_know": ["Deep space navigation"],
                        "falsely_believes": ["Asteroid 9 core is stable"]
                    }
                },
                "rumors_and_beliefs": [
                    {
                        "id": "RUMOR-01",
                        "claim": "Terminal Bay A has a secret smuggler hatch under Bay 3.",
                        "believed_by": "Dock workers in Terminal Bay",
                        "veracity": "true"
                    },
                    {
                        "id": "RUMOR-02",
                        "claim": "Asteroid 9 miners uncovered alien ruins inside the deep shaft.",
                        "believed_by": "Deep space scavengers",
                        "veracity": "false"
                    }
                ],
                "unresolved_mysteries": []
            }
            with open(os.path.join(wf_dir, "world_foundation.json"), "w", encoding="utf-8") as f:
                json.dump(wf_data, f)

            assembler = PromptAssembler(temp_dir)

            # 1. Unfiltered load includes all entities
            unfiltered = assembler.load_world_foundation("sandbox_camp", filter_relevant=False)
            self.assertIn("Terminal Bay Security", unfiltered)
            self.assertIn("Deep Asteroid 9 Miners", unfiltered)
            self.assertIn("officer_chen", unfiltered)
            self.assertIn("miner_jax", unfiltered)
            self.assertIn("Terminal Bay A has a secret smuggler hatch", unfiltered)
            self.assertIn("Asteroid 9 miners uncovered alien ruins", unfiltered)

            # 2. Filtered with scene anchor at Terminal Bay A
            scene_anchor = {
                "location": "Terminal Bay A Staging Room",
                "context": "Reviewing security manifests."
            }
            filtered = assembler.load_world_foundation("sandbox_camp", scene_anchor=scene_anchor, filter_relevant=True)

            # Core immutable facts and world state are ALWAYS included
            self.assertIn("IMMUTABLE FACTS", filtered)
            self.assertIn("Atmosphere requires station reactors", filtered)
            self.assertIn("MUTABLE WORLD STATE", filtered)

            # Relevant entities INCLUDED
            self.assertIn("Terminal Bay Security", filtered)
            self.assertIn("officer_chen", filtered)
            self.assertIn("Terminal Bay A has a secret smuggler hatch", filtered)

            # Irrelevant entities EXCLUDED
            self.assertNotIn("Deep Asteroid 9 Miners", filtered)
            self.assertNotIn("miner_jax", filtered)
            self.assertNotIn("Asteroid 9 miners uncovered alien ruins", filtered)

    def test_progressive_disclosure_active_conflicts(self):
        """Verifies active conflicts retain relevant factions even when location differs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "CAMPAIGNS", "conflict_camp")
            wf_dir = os.path.join(camp_dir, "WORLD_FOUNDATION")
            os.makedirs(wf_dir)

            wf_data = {
                "campaign_id": "conflict_camp",
                "schema_version": "1.0.0",
                "immutable_facts": [{"id": "F1", "statement": "Station core is active."}],
                "mutable_world_state": {"active_epoch": "Era 1"},
                "factions_and_tensions": [
                    {
                        "id": "shadow_syndicate",
                        "name": "Shadow Syndicate",
                        "agenda": "Subvert station authority.",
                        "tensions": [{"target_entity": "Transit Directorate", "source_of_friction": "Territory war"}]
                    },
                    {
                        "id": "farming_coop",
                        "name": "Hydroponic Farming Coop",
                        "agenda": "Grow algae protein in Sector 12.",
                        "tensions": []
                    }
                ],
                "npc_knowledge": {},
                "rumors_and_beliefs": []
            }
            with open(os.path.join(wf_dir, "world_foundation.json"), "w", encoding="utf-8") as f:
                json.dump(wf_data, f)

            assembler = PromptAssembler(temp_dir)

            # Neutral scene anchor but active conflict mentions Shadow Syndicate
            scene_anchor = {"location": "Neutral Transit Hub", "context": "Waiting for transport."}
            active_conflicts = ["Territory war against the Shadow Syndicate"]

            filtered = assembler.load_world_foundation(
                "conflict_camp",
                scene_anchor=scene_anchor,
                active_conflicts=active_conflicts,
                filter_relevant=True
            )

            self.assertIn("Shadow Syndicate", filtered)
            self.assertNotIn("Hydroponic Farming Coop", filtered)

    def test_prompt_caching_stable_prefix_order(self):
        """Verifies static prefix sections precede dynamic turn sections for prefix caching."""
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "CAMPAIGNS", "order_camp")
            os.makedirs(os.path.join(camp_dir, "GAMEPLAY"))
            os.makedirs(os.path.join(camp_dir, "IDEAS"))
            os.makedirs(os.path.join(camp_dir, "TURNS", "ACTIVE"))
            os.makedirs(os.path.join(camp_dir, "WORLD_FOUNDATION"))
            os.makedirs(os.path.join(camp_dir, "WORLD_BIBLE", "CORE"))
            os.makedirs(os.path.join(temp_dir, "GLOBAL"))

            with open(os.path.join(temp_dir, "GLOBAL", "CORE-001_HARD_CONSTRAINTS.md"), "w") as f:
                f.write("# Codex Constraints")
            with open(os.path.join(camp_dir, "AGENTS.md"), "w") as f:
                f.write("# Campaign Directives")
            with open(os.path.join(camp_dir, "campaign_config.json"), "w") as f:
                json.dump({"id": "order_camp", "metrics": []}, f)
            with open(os.path.join(camp_dir, "ontology.json"), "w") as f:
                json.dump({"disambiguation_rules": [{"rule_id": "R1", "operational_guardrail": "None"}]}, f)
            with open(os.path.join(camp_dir, "WORLD_FOUNDATION", "world_foundation.json"), "w") as f:
                json.dump({"immutable_facts": [{"id": "F1", "statement": "Station core"}]}, f)
            with open(os.path.join(camp_dir, "WORLD_BIBLE", "CORE", "primer.md"), "w") as f:
                f.write("# Lore Primer")
            with open(os.path.join(camp_dir, "GAMEPLAY", "status.md"), "w") as f:
                f.write("# Gameplay Status")
            with open(os.path.join(camp_dir, "IDEAS", "notes.md"), "w") as f:
                f.write("# Ideas")

            record_turn(camp_dir, 1, "Player action 1", "GM response 1")

            assembler = PromptAssembler(temp_dir)
            prompt = assembler.build_system_prompt(
                "order_camp",
                action="Inspect the datapad",
                turn=2,
                calibration_advisory="- Keep sentences concise"
            )

            idx_rules = prompt.find("GLOBAL SYSTEM CONSTRAINTS")
            idx_directives = prompt.find("CAMPAIGN-SPECIFIC DIRECTIVES")
            idx_metrics = prompt.find("CAMPAIGN METRICS & CONFIGURATION")
            idx_ontology = prompt.find("ONTOLOGY, KINSHIP")
            idx_foundation = prompt.find("WORLD FOUNDATION & EPISTEMIC BOUNDARIES")
            idx_lore = prompt.find("WORLD BIBLE & RELEVANT LORE")

            idx_turns = prompt.find("RECENT TURNS & IMMEDIATE HISTORY")
            idx_gameplay = prompt.find("ACTIVE CAMPAIGN GAMEPLAY & STATE")
            idx_ideas = prompt.find("STORY STEERING & NARRATIVE SEEDS")
            idx_advisory = prompt.find("DYNAMIC AGENT CALIBRATION ADVISORY")
            idx_action = prompt.find("CURRENT TURN ACTION")

            # Static Prefix comes first in deterministic order
            self.assertGreaterEqual(idx_rules, 0)
            self.assertGreater(idx_directives, idx_rules)
            self.assertGreater(idx_metrics, idx_directives)
            self.assertGreater(idx_ontology, idx_metrics)
            self.assertGreater(idx_foundation, idx_ontology)
            self.assertGreater(idx_lore, idx_foundation)

            # Dynamic Suffix comes after Static Prefix
            self.assertGreater(idx_turns, idx_lore)
            self.assertGreater(idx_gameplay, idx_lore)
            self.assertGreater(idx_ideas, idx_lore)
            self.assertGreater(idx_advisory, idx_ideas)
            self.assertGreater(idx_action, idx_advisory)

    def test_prompt_caching_prefix_byte_identity_across_turns(self):
        """Verifies static prefix is byte-for-byte identical across turns with varying dynamic inputs."""
        # Turn 1
        prefix_turn_1 = self.assembler.build_static_prefix("template_campaign")
        suffix_turn_1 = self.assembler.build_dynamic_suffix(
            "template_campaign",
            calibration_advisory="- Advisory Turn 1",
            action="Search the desk",
            turn=1
        )
        prompt_turn_1 = prefix_turn_1 + suffix_turn_1

        # Turn 2 (different action, different advisory, different turn number)
        prefix_turn_2 = self.assembler.build_static_prefix("template_campaign")
        suffix_turn_2 = self.assembler.build_dynamic_suffix(
            "template_campaign",
            calibration_advisory="- Advisory Turn 2: Do not use exclamation marks",
            action="Unlock the heavy blast door",
            turn=2
        )
        prompt_turn_2 = prefix_turn_2 + suffix_turn_2

        # 1. Static Prefix is 100% byte-for-byte identical
        self.assertEqual(prefix_turn_1, prefix_turn_2)
        self.assertTrue(prompt_turn_1.startswith(prefix_turn_1))
        self.assertTrue(prompt_turn_2.startswith(prefix_turn_2))

        # 2. Dynamic Suffixes differ
        self.assertNotEqual(suffix_turn_1, suffix_turn_2)
        self.assertIn("Search the desk", prompt_turn_1)
        self.assertNotIn("Unlock the heavy blast door", prompt_turn_1)
        self.assertIn("Unlock the heavy blast door", prompt_turn_2)
        self.assertNotIn("Search the desk", prompt_turn_2)



if __name__ == "__main__":
    unittest.main()
