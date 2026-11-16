#!/usr/bin/env python3
"""
Unit tests for agent skill definitions, AGENTS.md directives,
and role demarcation contracts (Issue #33).
"""

import os
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestSkillsAndDirectives(unittest.TestCase):
    def test_world_architect_skill_exists_and_codifies_directives(self):
        skill_path = os.path.join(ROOT_DIR, ".agent", "skills", "world-architect", "SKILL.md")
        self.assertTrue(os.path.isfile(skill_path), f"Missing skill file at {skill_path}")

        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Frontmatter
        self.assertIn("name: world-architect", content)

        # Core responsibilities & scope
        self.assertIn("world_foundation.json", content)
        self.assertIn("ontology.json", content)
        self.assertIn("campaign_config.json", content)
        self.assertIn("WORLD_BIBLE", content)

        # Turn 1 Hard Stop Rule
        self.assertIn("Turn 1 Hard Stop Rule", content)
        self.assertIn("turn_0001.md", content)
        self.assertIn("cyoa-gm", content)

        # Player Choice Exclusivity
        self.assertIn("Player Choice Exclusivity", content)

    def test_agents_md_role_matrix_and_gates(self):
        agents_path = os.path.join(ROOT_DIR, "AGENTS.md")
        self.assertTrue(os.path.isfile(agents_path), f"Missing AGENTS.md at {agents_path}")

        with open(agents_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Upfront Role Selection Matrix
        self.assertIn("Role Selection Matrix", content)
        self.assertIn("world-architect", content)
        self.assertIn("cyoa-gm", content)
        self.assertIn("shadow-narrator", content)

        # Player Choice Exclusivity Rule
        self.assertIn("PLAYER CHOICE EXCLUSIVITY RULE", content)

        # Shadow Narrator Explicit Permission Gate
        self.assertIn("SHADOW NARRATOR EXPLICIT PERMISSION GATE", content)

        # Turn 1 Hard Stop Rule
        self.assertIn("TURN 1 HARD STOP RULE", content)

    def test_cyoa_gm_skill_reflects_choice_exclusivity(self):
        skill_path = os.path.join(ROOT_DIR, ".agent", "skills", "cyoa-gm", "SKILL.md")
        self.assertTrue(os.path.isfile(skill_path), f"Missing skill file at {skill_path}")

        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Player Choice Exclusivity", content)
        self.assertIn("Explicit Permission Gate", content)

    def test_shadow_narrator_skill_reflects_rules(self):
        skill_path = os.path.join(ROOT_DIR, ".agent", "skills", "shadow-narrator", "SKILL.md")
        self.assertTrue(os.path.isfile(skill_path), f"Missing skill file at {skill_path}")

        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Player Choice Exclusivity", content)
        self.assertIn("Explicit Permission Gate", content)


if __name__ == "__main__":
    unittest.main()
