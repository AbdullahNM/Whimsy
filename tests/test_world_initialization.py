#!/usr/bin/env python3
"""
Unit tests for World-First Campaign Initialization and Epistemic Separation.
Tests:
1. Schema validation of world_foundation.json against GLOBAL/SCHEMAS/world_foundation.schema.json.
2. World-first initialization without predetermined protagonist storyline (autonomous simulation).
3. Epistemic separation between immutable facts, mutable state, rumors, NPC knowledge boundaries,
   and hidden canon secrets/mysteries in ENGINE/prompt_assembler.py.
"""

import os
import sys
import json
import unittest
import tempfile
import copy

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.prompt_assembler import PromptAssembler, assemble_prompt
from tests.test_schemas import SimpleSchemaValidator


class TestWorldInitialization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema_path = os.path.join(ROOT_DIR, "GLOBAL", "SCHEMAS", "world_foundation.schema.json")
        with open(cls.schema_path, "r", encoding="utf-8") as f:
            cls.world_foundation_schema = json.load(f)

        cls.template_wf_path = os.path.join(
            ROOT_DIR, "CAMPAIGNS", "template_campaign", "WORLD_FOUNDATION", "world_foundation.json"
        )
        with open(cls.template_wf_path, "r", encoding="utf-8") as f:
            cls.template_wf_data = json.load(f)

        cls.assembler = PromptAssembler(ROOT_DIR)

    # =========================================================================
    # 1. Schema Validation Tests
    # =========================================================================

    def test_template_world_foundation_schema_valid(self):
        """The bundled template campaign's world_foundation.json must strictly pass schema validation."""
        errors = SimpleSchemaValidator.validate(self.template_wf_data, self.world_foundation_schema)
        self.assertEqual(errors, [], f"Schema validation errors in template world_foundation: {errors}")
        self.assertEqual(self.template_wf_data["campaign_id"], "template_campaign")
        self.assertEqual(self.template_wf_data["schema_version"], "1.0.0")

    def test_schema_missing_required_top_level_fields(self):
        """Omitting any of the required world foundation keys must result in validation errors."""
        required_keys = [
            "campaign_id",
            "schema_version",
            "immutable_facts",
            "mutable_world_state",
            "factions_and_tensions",
            "npc_knowledge",
            "rumors_and_beliefs",
            "unresolved_mysteries",
        ]
        for req in required_keys:
            bad_data = copy.deepcopy(self.template_wf_data)
            del bad_data[req]
            errors = SimpleSchemaValidator.validate(bad_data, self.world_foundation_schema)
            self.assertTrue(
                any(f"missing required property '{req}'" in e for e in errors),
                f"Expected missing required property error for '{req}', got {errors}"
            )

    def test_schema_invalid_immutable_fact_category(self):
        """Immutable facts must only allow valid enum categories."""
        bad_data = copy.deepcopy(self.template_wf_data)
        bad_data["immutable_facts"][0]["category"] = "unsupported_fiction"
        errors = SimpleSchemaValidator.validate(bad_data, self.world_foundation_schema)
        self.assertTrue(any("not in enum" in e for e in errors))

    def test_schema_invalid_rumor_veracity(self):
        """Rumor veracity must be one of the specified enum values."""
        bad_data = copy.deepcopy(self.template_wf_data)
        bad_data["rumors_and_beliefs"][0]["veracity"] = "absolute_truth"
        errors = SimpleSchemaValidator.validate(bad_data, self.world_foundation_schema)
        self.assertTrue(any("not in enum" in e for e in errors))

    def test_schema_invalid_faction_tension_intensity(self):
        """Faction tension intensity must belong to the allowed intensity enum."""
        bad_data = copy.deepcopy(self.template_wf_data)
        bad_data["factions_and_tensions"][0]["tensions"][0]["intensity"] = "nuclear"
        errors = SimpleSchemaValidator.validate(bad_data, self.world_foundation_schema)
        self.assertTrue(any("not in enum" in e for e in errors))

    def test_schema_npc_knowledge_missing_epistemic_quadrants(self):
        """NPC knowledge entries must include knows, does_not_know, and falsely_believes."""
        bad_data = copy.deepcopy(self.template_wf_data)
        del bad_data["npc_knowledge"]["handler_cross"]["falsely_believes"]
        errors = SimpleSchemaValidator.validate(bad_data, self.world_foundation_schema)
        self.assertTrue(any("missing required property 'falsely_believes'" in e for e in errors))

    # =========================================================================
    # 2. World-First Campaign Initialization (No Predetermined Storyline)
    # =========================================================================

    def test_campaign_loads_without_predetermined_protagonist_storyline(self):
        """
        Verify that a campaign can be fully initialized and loaded in emergent sandbox mode:
        The world exists with immutable laws, active factions, tensions, and world state
        WITHOUT any predetermined protagonist storyline or narrative steering.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "CAMPAIGNS", "emergent_sandbox")
            wf_dir = os.path.join(camp_dir, "WORLD_FOUNDATION")
            os.makedirs(wf_dir, exist_ok=True)
            os.makedirs(os.path.join(camp_dir, "GAMEPLAY"), exist_ok=True)
            os.makedirs(os.path.join(temp_dir, "GLOBAL"), exist_ok=True)

            # Minimal global constraints
            with open(os.path.join(temp_dir, "GLOBAL", "CORE-001_HARD_CONSTRAINTS.md"), "w") as f:
                f.write("# Sandbox Engine Constraints")

            # World-first foundation with NO protagonist storyline
            emergent_wf = {
                "campaign_id": "emergent_sandbox",
                "schema_version": "1.0.0",
                "world_name": "Autonomous Frontier Outpost",
                "overview": "Living frontier colony operating on autonomous economic and political currents.",
                "immutable_facts": [
                    {
                        "id": "ASTRONOMY-01",
                        "category": "natural_laws",
                        "statement": "The twin suns set every 38 hours, producing an 8-hour solar blackout."
                    }
                ],
                "mutable_world_state": {
                    "active_epoch": "Solar Cycle Zero — Deep Dry Season",
                    "factions_control": {
                        "Solar Guild": "Full control of the central hydro-distillery",
                        "Frontier Scavengers": "Dispersed control of the dune perimeter"
                    },
                    "resource_distribution": {
                        "potable_water": "Scarcity index 85/100",
                        "fuel_cells": "Available at premium tariffs"
                    },
                    "global_tensions_index": "Simmering water rationing disputes",
                    "dynamic_flags": {
                        "sandstorm_imminent": True
                    }
                },
                "factions_and_tensions": [
                    {
                        "id": "solar_guild",
                        "name": "Solar Guild",
                        "agenda": "Monopolize water extraction and levy water tokens on all inhabitants.",
                        "objectives": [
                            "Construct high-pressure reservoir in Sector 3",
                            "Enforce daylight curfew during blackout hours"
                        ],
                        "tensions": [
                            {
                                "target_entity": "Frontier Scavengers",
                                "source_of_friction": "Raids on moisture vaporators",
                                "intensity": "simmering"
                            }
                        ]
                    }
                ],
                "npc_knowledge": {
                    "guildmaster_tarek": {
                        "knows": ["Reservoir water levels are at 18%"],
                        "does_not_know": ["Scavengers have tunneled into the secondary cistern"],
                        "falsely_believes": ["Believes Scavengers are unorganized and lack weaponry"]
                    }
                },
                "rumors_and_beliefs": [
                    {
                        "id": "RUMOR-S01",
                        "claim": "An ancient subterranean aquifer lies beneath the southern salt flats.",
                        "believed_by": "Frontier prospectors",
                        "veracity": "partially_true"
                    }
                ],
                "unresolved_mysteries": [
                    {
                        "id": "SECRET-S01",
                        "title": "Origin of the Drought",
                        "secret_truth": "The orbital mirror array was intentionally misaligned 10 years ago.",
                        "discovered": False,
                        "discovery_conditions": "Access satellite telemetry terminal in High Spire."
                    }
                ]
            }

            wf_file = os.path.join(wf_dir, "world_foundation.json")
            with open(wf_file, "w", encoding="utf-8") as f:
                json.dump(emergent_wf, f, indent=2)

            # Notice: NO IDEAS/narrative_steering.md created! No predetermined protagonist quest!
            temp_assembler = PromptAssembler(temp_dir)
            wf_output = temp_assembler.load_world_foundation("emergent_sandbox")

            # World foundation must load completely
            self.assertIn("=== WORLD FOUNDATION & EPISTEMIC SEPARATION ===", wf_output)
            self.assertIn("ASTRONOMY-01", wf_output)
            self.assertIn("Solar Guild", wf_output)
            self.assertIn("Solar Cycle Zero", wf_output)
            self.assertIn("Autonomous Objectives", wf_output)
            self.assertIn("guildmaster_tarek", wf_output)

            # Build full system prompt without any protagonist storyline
            prompt = temp_assembler.build_system_prompt("emergent_sandbox")
            self.assertIn("GLOBAL SYSTEM CONSTRAINTS", prompt)
            self.assertIn("WORLD FOUNDATION & EPISTEMIC BOUNDARIES", prompt)
            self.assertIn("The twin suns set every 38 hours", prompt)

    # =========================================================================
    # 3. Epistemic Separation in Prompt Assembler
    # =========================================================================

    def test_epistemic_separation_categories_rendered(self):
        """PromptAssembler must format all six epistemic categories distinctly."""
        wf_text = self.assembler.load_world_foundation("template_campaign")

        # 1. Immutable Facts
        self.assertIn("## 1. IMMUTABLE FACTS (UNALTERABLE GROUND TRUTHS)", wf_text)
        self.assertIn("[FACT-01] [GEOGRAPHY]", wf_text)
        self.assertIn("four concentric subterranean rings", wf_text)

        # 2. Mutable World State
        self.assertIn("## 2. MUTABLE WORLD STATE (DYNAMIC GEOPOLITICAL & ENVIRONMENTAL STATE)", wf_text)
        self.assertIn("Cycle 143", wf_text)
        self.assertIn("Central Transit Directorate", wf_text)

        # 3. Independent Factions & Active Tensions
        self.assertIn("## 3. INDEPENDENT FACTIONS & ACTIVE TENSIONS", wf_text)
        self.assertIn("Autonomous Objectives", wf_text)
        self.assertIn("Tension with Central Transit Directorate [escalating]", wf_text)

        # 4. NPC Epistemic Knowledge Map
        self.assertIn("## 4. NPC EPISTEMIC KNOWLEDGE MAP (BOUNDARIES & MISCONCEPTIONS)", wf_text)
        self.assertIn("handler_cross", wf_text)
        self.assertIn("Verified Known Truths", wf_text)
        self.assertIn("Ignorant Of (Does NOT Know)", wf_text)
        self.assertIn("False Beliefs (Misconceptions)", wf_text)

        # 5. Rumors & Beliefs
        self.assertIn("## 5. RUMORS, FOLKTALES & SUBJECTIVE BELIEFS", wf_text)
        self.assertIn("Veracity: partially_true", wf_text)
        self.assertIn("Veracity: exaggerated", wf_text)

        # 6. Unresolved Mysteries
        self.assertIn("## 6. CANON SECRETS & UNRESOLVED MYSTERIES", wf_text)

    def test_epistemic_separation_mysteries_hidden_unless_discovered(self):
        """Canon mysteries must be flagged as HIDDEN FROM PROTAGONIST VIEW unless discovered: true."""
        wf_text = self.assembler.load_world_foundation("template_campaign")

        # Undiscovered mysteries in template must be strictly hidden
        self.assertIn("[HIDDEN FROM PROTAGONIST VIEW - CANON SECRET] **The Sub-Level 8 Deep Core Protocol**", wf_text)
        self.assertIn("[HIDDEN FROM PROTAGONIST VIEW - CANON SECRET] **Container Sigma-9 Manifest Discrepancy**", wf_text)
        self.assertNotIn("[DISCOVERED]", wf_text)

        # Now test that a discovered mystery renders as [DISCOVERED]
        with tempfile.TemporaryDirectory() as temp_dir:
            camp_dir = os.path.join(temp_dir, "CAMPAIGNS", "discovery_test")
            wf_dir = os.path.join(camp_dir, "WORLD_FOUNDATION")
            os.makedirs(wf_dir, exist_ok=True)

            discovered_wf = copy.deepcopy(self.template_wf_data)
            discovered_wf["unresolved_mysteries"][0]["discovered"] = True

            with open(os.path.join(wf_dir, "world_foundation.json"), "w", encoding="utf-8") as f:
                json.dump(discovered_wf, f, indent=2)

            temp_assembler = PromptAssembler(temp_dir)
            disc_text = temp_assembler.load_world_foundation("discovery_test")

            self.assertIn("[DISCOVERED] **The Sub-Level 8 Deep Core Protocol**", disc_text)
            self.assertIn("[HIDDEN FROM PROTAGONIST VIEW - CANON SECRET] **Container Sigma-9 Manifest Discrepancy**", disc_text)

    def test_epistemic_separation_false_beliefs_not_immutable_facts(self):
        """An NPC's false beliefs or subjective rumors must not be listed as immutable facts."""
        wf_text = self.assembler.load_world_foundation("template_campaign")

        # Split output into sections
        sections = wf_text.split("## ")
        immutable_section = next((s for s in sections if s.startswith("1. IMMUTABLE FACTS")), "")
        npc_section = next((s for s in sections if s.startswith("4. NPC EPISTEMIC KNOWLEDGE MAP")), "")
        rumor_section = next((s for s in sections if s.startswith("5. RUMORS")), "")

        # Mercer's false belief that Bay A contract is routine
        self.assertIn("routine equipment transport job", npc_section)
        self.assertNotIn("routine equipment transport job", immutable_section)

        # Cross's false belief about Bay A camera coverage
        self.assertIn("blind spot exists at Vent shaft 3", npc_section)
        self.assertNotIn("blind spot exists at Vent shaft 3", immutable_section)

        # Rumors must be in rumor section, not immutable section
        self.assertIn("rogue AI core", rumor_section)
        self.assertNotIn("rogue AI core", immutable_section)

    def test_prompt_assembler_missing_world_foundation_graceful(self):
        """PromptAssembler returns empty string without crashing if world foundation is absent."""
        empty_res = self.assembler.load_world_foundation("completely_fictional_campaign")
        self.assertEqual(empty_res, "")

    def test_build_system_prompt_includes_world_foundation(self):
        """The assembled system prompt for template_campaign must contain the world foundation block."""
        prompt = self.assembler.build_system_prompt("template_campaign")
        self.assertIn("# 3.1 WORLD FOUNDATION & EPISTEMIC BOUNDARIES", prompt)
        self.assertIn("=== WORLD FOUNDATION & EPISTEMIC SEPARATION ===", prompt)
        self.assertIn("four concentric subterranean rings", prompt)


if __name__ == "__main__":
    unittest.main()
