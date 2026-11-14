#!/usr/bin/env python3
"""
Unit tests for ENGINE/graph_validator.py and ENGINE/graph_export.py.
Tests detection of:
- Unreachable passages (orphans)
- Dead ends missing terminal/end tags
- Broken links pointing to non-existent passages
- Choice text collisions
- Inescapable dead cycles
- Valid graphs and DOT / HTML visualization generation
"""

import os
import sys
import json
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.twine_io import parse_twine_html
from ENGINE.graph_validator import (
    GraphValidator,
    validate_graph,
    validate_campaign,
    Diagnostic,
    ValidationResult
)
from ENGINE.graph_export import to_dot, to_html_view, export_to_dot, export_to_html_view


class TestGraphValidator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures_dir = os.path.join(ROOT_DIR, "tests", "fixtures", "twine")

    def _load_fixture(self, filename: str):
        path = os.path.join(self.fixtures_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            return parse_twine_html(f.read())

    # --------------------------------------------------------------------------
    # Valid Fixture Tests
    # --------------------------------------------------------------------------

    def test_minimal_valid_graph_passes_validation(self):
        graph = self._load_fixture("minimal_valid.html")
        res = validate_graph(graph)
        self.assertTrue(res.valid, f"Expected valid graph, got errors: {res.errors}")
        self.assertEqual(len(res.errors), 0)

    def test_aurelian_academy_passes_validation(self):
        graph = self._load_fixture("aurelian_academy.html")
        res = validate_graph(graph)
        self.assertTrue(res.valid, f"Expected Aurelian Academy to pass, got errors: {[e.message for e in res.errors]}")
        self.assertEqual(len(res.errors), 0)

    # --------------------------------------------------------------------------
    # Deliberately Broken Fixtures Tests
    # --------------------------------------------------------------------------

    def test_detection_of_unreachable_passages_orphans(self):
        graph = self._load_fixture("broken_orphan.html")
        file_refs = {"Orphaned Crypt": "CAMPAIGNS/test/TURNS/ACTIVE/turn_0003.md"}
        res = validate_graph(graph, file_references=file_refs)

        self.assertFalse(res.valid)
        orphan_errors = [d for d in res.errors if d.code == "UNREACHABLE_PASSAGE"]
        self.assertTrue(len(orphan_errors) >= 2)

        orphan_names = [d.passage_name for d in orphan_errors]
        self.assertIn("Orphaned Crypt", orphan_names)
        self.assertIn("Lost Chamber", orphan_names)

        # Check structured diagnostic fields and file reference
        crypt_diag = next(d for d in orphan_errors if d.passage_name == "Orphaned Crypt")
        self.assertEqual(crypt_diag.severity, "error")
        self.assertEqual(crypt_diag.passage_id, 3)
        self.assertEqual(crypt_diag.file, "CAMPAIGNS/test/TURNS/ACTIVE/turn_0003.md")

    def test_detection_of_dead_end_missing_terminal_tag(self):
        graph = self._load_fixture("broken_dead_end.html")
        res = validate_graph(graph)

        self.assertFalse(res.valid)
        dead_end_errors = [d for d in res.errors if d.code == "MISSING_TERMINAL_TAG"]
        self.assertTrue(len(dead_end_errors) >= 1)

        alley_diag = dead_end_errors[0]
        self.assertEqual(alley_diag.passage_name, "Blind Alley")
        self.assertEqual(alley_diag.passage_id, 3)
        self.assertIn("zero outgoing choices", alley_diag.message)

    def test_detection_of_broken_links(self):
        graph = self._load_fixture("broken_link.html")
        res = validate_graph(graph)

        self.assertFalse(res.valid)
        broken_link_errors = [d for d in res.errors if d.code == "BROKEN_LINK"]
        self.assertTrue(len(broken_link_errors) >= 1)

        diag = broken_link_errors[0]
        self.assertEqual(diag.passage_name, "Corridor")
        self.assertEqual(diag.target, "NonExistentVoid")
        self.assertIn("NonExistentVoid", diag.message)

    def test_detection_of_choice_text_collisions(self):
        graph = self._load_fixture("broken_collision.html")
        res = validate_graph(graph)

        self.assertFalse(res.valid)
        collision_errors = [d for d in res.errors if d.code == "CHOICE_COLLISION"]
        self.assertTrue(len(collision_errors) >= 1)

        diag = collision_errors[0]
        self.assertEqual(diag.passage_name, "Crossroads")
        self.assertIn("collides with", diag.message)

    def test_detection_of_dead_cycles(self):
        graph = self._load_fixture("broken_cycle.html")
        res = validate_graph(graph)

        self.assertFalse(res.valid)
        cycle_errors = [d for d in res.errors if d.code == "DEAD_CYCLE"]
        self.assertTrue(len(cycle_errors) >= 1)

        diag = cycle_errors[0]
        self.assertIn("Cycle with no escape detected", diag.message)
        self.assertIn("Chamber Alpha", diag.message)
        self.assertIn("Chamber Beta", diag.message)

    # --------------------------------------------------------------------------
    # Campaign Validation Tests
    # --------------------------------------------------------------------------

    def test_validate_campaign_template(self):
        res = validate_campaign("template_campaign", root_dir=ROOT_DIR)
        # Template campaign has a start turn and connected target stub with terminal tag
        self.assertTrue(res.valid, f"Template campaign errors: {[d.message for d in res.errors]}")

    # --------------------------------------------------------------------------
    # Graph Visualization Export Tests (to_dot and to_html_view)
    # --------------------------------------------------------------------------

    def test_to_dot_export(self):
        graph = self._load_fixture("aurelian_academy.html")
        dot_str = to_dot(graph)

        self.assertTrue(dot_str.startswith("digraph StoryGraph {"))
        self.assertIn("Academy Gates", dot_str)
        self.assertIn("Valedictorian Ending", dot_str)
        self.assertIn("->", dot_str)
        self.assertTrue(dot_str.strip().endswith("}"))

    def test_to_html_view_renders_all_passages_of_aurelian_academy(self):
        graph = self._load_fixture("aurelian_academy.html")
        html_str = to_html_view(graph)

        self.assertIn("<!DOCTYPE html>", html_str)
        self.assertIn("Aurelian Academy", html_str)
        self.assertIn("12 Passages", html_str)
        self.assertIn("Academy Gates", html_str)
        self.assertIn("Valedictorian Ending", html_str)
        self.assertIn("Grand Library", html_str)

        # SVG canvas elements
        self.assertIn("<svg id=\"graph-svg\">", html_str)
        self.assertIn("class=\"node-group\"", html_str)
        self.assertIn("class=\"edge\"", html_str)

        # Standalone requirement: no external script CDN tags
        self.assertNotIn("https://cdn.", html_str)
        self.assertNotIn("http://cdn.", html_str)


if __name__ == "__main__":
    unittest.main()
