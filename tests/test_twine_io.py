#!/usr/bin/env python3
"""
Unit tests for ENGINE/twine_io.py
Tests Twine 2 HTML archive parsing, emission, campaign export, import,
round-trip fidelity, story-format neutrality, macro warnings, and CLI.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import subprocess

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.twine_io import (
    StoryGraph,
    PassageNode,
    StoryLink,
    parse_twine_html,
    emit_twine_html,
    parse_passage_links,
    parse_passage_variables,
    parse_tags_metadata,
    format_metadata_tags,
    export_campaign_to_graph,
    export_campaign_to_archive,
    import_archive_to_campaign,
)
from tests.test_schemas import SimpleSchemaValidator


class TestTwineIO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures_dir = os.path.join(ROOT_DIR, "tests", "fixtures", "twine")
        schema_path = os.path.join(ROOT_DIR, "GLOBAL", "SCHEMAS", "story_graph.schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            cls.story_graph_schema = json.load(f)

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="twine_test_")

    def tearDown(self):
        if os.path.isdir(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # Link and Variable Extraction Unit Tests
    # --------------------------------------------------------------------------

    def test_link_extraction_all_syntaxes(self):
        text = """
        Standard: [[Proceed to Chapel->Chapel]]
        Reverse: [[Courtyard<-Retreat to Courtyard]]
        Pipe: [[Option Label|Library]]
        Bare: [[Sanctum]]
        SugarCube Two: <<link "Inspect desk" "Office Desk">>
        SugarCube One: <<link "Great Hall">>
        SugarCube Bracket: <<link "Examine books" [[Restricted Section]]>>
        """
        links = parse_passage_links(text)
        targets = [lk.target for lk in links]
        labels = [lk.text for lk in links]

        self.assertIn("Chapel", targets)
        self.assertIn("Proceed to Chapel", labels)

        self.assertIn("Courtyard", targets)
        self.assertIn("Retreat to Courtyard", labels)

        self.assertIn("Library", targets)
        self.assertIn("Option Label", labels)

        self.assertIn("Sanctum", targets)

        self.assertIn("Office Desk", targets)
        self.assertIn("Inspect desk", labels)

        self.assertIn("Great Hall", targets)
        self.assertIn("Restricted Section", targets)

    def test_variable_extraction_harlowe_and_sugarcube(self):
        text = """
        (set: $sanity to 75)
        (set: $has_badge to true)
        (set: $player_alias to "Phantom")
        <<set $credits = 500>>
        <<set $energy = 90.5>>
        <<set $infiltrated = false>>
        """
        variables = parse_passage_variables(text)
        self.assertEqual(variables.get("sanity"), 75)
        self.assertEqual(variables.get("has_badge"), True)
        self.assertEqual(variables.get("player_alias"), "Phantom")
        self.assertEqual(variables.get("credits"), 500)
        self.assertEqual(variables.get("energy"), 90.5)
        self.assertEqual(variables.get("infiltrated"), False)

    def test_tags_metadata_parsing(self):
        tags = "mode:classic_cyoa location:academy_gate faction:scholars intensity:3 clock:curfew terminal"
        tag_list, meta = parse_tags_metadata(tags)

        self.assertEqual(meta.get("mode"), "classic_cyoa")
        self.assertEqual(meta.get("location"), "academy_gate")
        self.assertEqual(meta.get("faction"), "scholars")
        self.assertEqual(meta.get("intensity"), 3)
        self.assertIn("curfew", meta.get("clocks", []))
        self.assertTrue(meta.get("terminal"))

        # Re-formatting tags should round-trip
        formatted = format_metadata_tags(meta)
        self.assertIn("mode:classic_cyoa", formatted)
        self.assertIn("location:academy_gate", formatted)
        self.assertIn("intensity:3", formatted)
        self.assertIn("terminal", formatted)

    # --------------------------------------------------------------------------
    # Fixture Parsing Tests
    # --------------------------------------------------------------------------

    def test_parse_minimal_valid_fixture(self):
        fixture_path = os.path.join(self.fixtures_dir, "minimal_valid.html")
        with open(fixture_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        graph = parse_twine_html(html_content)
        self.assertEqual(graph.name, "Minimal Valid Story")
        self.assertEqual(graph.startnode, "1")
        self.assertEqual(len(graph.passages), 5)

        start_p = graph.get_passage(1)
        self.assertIsNotNone(start_p)
        self.assertEqual(start_p.name, "Entrance Hall")
        self.assertEqual(len(start_p.links), 2)

        vault_p = graph.get_passage("Vault Ending")
        self.assertIsNotNone(vault_p)
        self.assertTrue(vault_p.metadata.get("terminal"))

    def test_parse_aurelian_academy_fixture(self):
        fixture_path = os.path.join(self.fixtures_dir, "aurelian_academy.html")
        with open(fixture_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        graph = parse_twine_html(html_content)
        self.assertEqual(graph.name, "Aurelian Academy")
        self.assertEqual(len(graph.passages), 12)

        # Start passage variables
        start_p = graph.get_start_passage()
        self.assertIsNotNone(start_p)
        self.assertEqual(start_p.variables.get("scholarly_prestige"), 10)
        self.assertEqual(start_p.variables.get("energy"), 100)

        # Check schema validity
        schema_errors = SimpleSchemaValidator.validate(graph.to_dict(), self.story_graph_schema)
        self.assertEqual(schema_errors, [], f"Schema validation errors: {schema_errors}")

    def test_story_format_neutrality_unsupported_macros(self):
        sc_fixture = os.path.join(self.fixtures_dir, "sugarcube_macros.html")
        with open(sc_fixture, "r", encoding="utf-8") as f:
            html_content = f.read()

        graph = parse_twine_html(html_content)
        # Unsupported macros (print, if, widget) must produce warnings, not crash
        self.assertTrue(len(graph.warnings) > 0)
        self.assertTrue(any("print" in w for w in graph.warnings))
        self.assertTrue(any("widget" in w for w in graph.warnings))

        # Narrative text must preserve macros intact
        start_p = graph.get_passage("Starting Office")
        self.assertIn("<<print $player_name>>", start_p.text)
        self.assertIn("<<if $security_clearance > 1>>", start_p.text)

    # --------------------------------------------------------------------------
    # Round-trip Fidelity Tests (Twine -> StoryGraph -> Twine)
    # --------------------------------------------------------------------------

    def test_round_trip_html_storygraph_html(self):
        fixture_path = os.path.join(self.fixtures_dir, "aurelian_academy.html")
        with open(fixture_path, "r", encoding="utf-8") as f:
            orig_html = f.read()

        graph1 = parse_twine_html(orig_html)
        emitted_html = emit_twine_html(graph1)

        graph2 = parse_twine_html(emitted_html)

        self.assertEqual(graph1.name, graph2.name)
        self.assertEqual(graph1.startnode, graph2.startnode)
        self.assertEqual(len(graph1.passages), len(graph2.passages))

        for name, p1 in graph1.passages.items():
            p2 = graph2.get_passage(name)
            self.assertIsNotNone(p2, f"Passage '{name}' missing after round-trip")
            self.assertEqual(p1.pid, p2.pid)
            self.assertEqual(p1.variables, p2.variables)
            self.assertEqual(len(p1.links), len(p2.links))
            for lk1, lk2 in zip(p1.links, p2.links):
                self.assertEqual(lk1.text, lk2.text)
                self.assertEqual(lk1.target, lk2.target)

    # --------------------------------------------------------------------------
    # Campaign Export and Import Tests
    # --------------------------------------------------------------------------

    def test_export_template_campaign(self):
        graph = export_campaign_to_graph("template_campaign", root_dir=ROOT_DIR)
        self.assertIsNotNone(graph)
        self.assertEqual(graph.name, "New Campaign Universe")
        self.assertIn("Turn 1", graph.passages)

        out_html = os.path.join(self.temp_dir, "template_campaign.html")
        export_campaign_to_archive("template_campaign", out_html, root_dir=ROOT_DIR)
        self.assertTrue(os.path.isfile(out_html))
        self.assertGreater(os.path.getsize(out_html), 500)

        # Validate exported file can be parsed
        with open(out_html, "r", encoding="utf-8") as f:
            parsed = parse_twine_html(f.read())
        self.assertIn("Turn 1", parsed.passages)

    def test_import_archive_to_new_campaign_and_round_trip(self):
        fixture_path = os.path.join(self.fixtures_dir, "aurelian_academy.html")
        test_campaign_id = "test_aurelian_import"

        # Import archive
        imported_graph = import_archive_to_campaign(
            fixture_path,
            test_campaign_id,
            root_dir=self.temp_dir
        )
        self.assertEqual(len(imported_graph.passages), 12)

        campaign_dir = os.path.join(self.temp_dir, "CAMPAIGNS", test_campaign_id)
        self.assertTrue(os.path.isdir(campaign_dir))

        # Check required files generated
        config_file = os.path.join(campaign_dir, "campaign_config.json")
        status_file = os.path.join(campaign_dir, "GAMEPLAY", "status.json")
        story_graph_file = os.path.join(campaign_dir, "GAMEPLAY", "story_graph.json")
        active_turns_dir = os.path.join(campaign_dir, "TURNS", "ACTIVE")

        self.assertTrue(os.path.isfile(config_file))
        self.assertTrue(os.path.isfile(status_file))
        self.assertTrue(os.path.isfile(story_graph_file))
        self.assertTrue(os.path.isdir(active_turns_dir))

        # Verify story_graph.json adheres to schema
        with open(story_graph_file, "r", encoding="utf-8") as f:
            sg_data = json.load(f)
        errors = SimpleSchemaValidator.validate(sg_data, self.story_graph_schema)
        self.assertEqual(errors, [], f"Imported story_graph schema errors: {errors}")

        # Check turn files created
        turn_files = os.listdir(active_turns_dir)
        self.assertEqual(len(turn_files), 12)

        # Export back to HTML archive and verify fidelity
        re_exported_html = os.path.join(self.temp_dir, "re_exported.html")
        export_campaign_to_archive(test_campaign_id, re_exported_html, root_dir=self.temp_dir)
        self.assertTrue(os.path.isfile(re_exported_html))

        with open(re_exported_html, "r", encoding="utf-8") as f:
            re_parsed = parse_twine_html(f.read())

        self.assertEqual(len(imported_graph.passages), len(re_parsed.passages))
        for p_name, orig_p in imported_graph.passages.items():
            re_p = re_parsed.get_passage(p_name)
            self.assertIsNotNone(re_p, f"Passage {p_name} missing after export")
            self.assertEqual(orig_p.variables, re_p.variables)
            self.assertEqual([lk.target for lk in orig_p.links], [lk.target for lk in re_p.links])

    # --------------------------------------------------------------------------
    # CLI Tests
    # --------------------------------------------------------------------------

    def test_cli_export_and_import(self):
        out_html = os.path.join(self.temp_dir, "cli_exported.html")
        env = dict(os.environ, PYTHONPATH=ROOT_DIR, PYTHONUTF8="1")

        # CLI export
        cmd_export = [
            sys.executable, "-m", "ENGINE.twine_io",
            "export",
            "--campaign", "template_campaign",
            "--out", out_html,
            "--root", ROOT_DIR,
            "--validate"
        ]
        res_exp = subprocess.run(cmd_export, capture_output=True, text=True, env=env)
        self.assertEqual(res_exp.returncode, 0, f"CLI export failed: {res_exp.stderr}\n{res_exp.stdout}")
        self.assertTrue(os.path.isfile(out_html))

        # CLI import
        cmd_import = [
            sys.executable, "-m", "ENGINE.twine_io",
            "import",
            "--archive", out_html,
            "--campaign", "cli_test_campaign",
            "--root", self.temp_dir,
            "--validate"
        ]
        res_imp = subprocess.run(cmd_import, capture_output=True, text=True, env=env)
        self.assertEqual(res_imp.returncode, 0, f"CLI import failed: {res_imp.stderr}\n{res_imp.stdout}")
        self.assertTrue(os.path.isdir(os.path.join(self.temp_dir, "CAMPAIGNS", "cli_test_campaign")))


if __name__ == "__main__":
    unittest.main()
