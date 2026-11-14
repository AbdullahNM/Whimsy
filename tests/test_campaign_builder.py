#!/usr/bin/env python3
"""
Unit tests for campaign builder, shadow narrator advisory,
and engine server endpoints /init_campaign and /shadow/consult.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.campaign_builder import scaffold_campaign, consult_shadow_narrator
from tests.test_engine_server import execute_request


class TestCampaignBuilder(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_scaffold_campaign_creates_valid_structure(self):
        params = {
            "campaign_id": "test_stellar_voyage",
            "title": "Stellar Voyage",
            "genre": "Hard Sci-Fi",
            "operational_mode": "classic_cyoa",
            "pacing_profile": "tactical",
            "purse": "1,200 Sol Credits",
            "protagonist_name": "Commander Vane",
            "protagonist_role": "Starship Navigator",
            "premise": "Docked at Kepler Station preparing for warp.",
            "location": "Kepler Station Docking Bay 9"
        }

        result = scaffold_campaign(self.test_dir, params)
        self.assertEqual(result["campaign_id"], "test_stellar_voyage")
        self.assertEqual(result["title"], "Stellar Voyage")

        # Verify directories exist
        c_dir = os.path.join(self.test_dir, "CAMPAIGNS", "test_stellar_voyage")
        self.assertTrue(os.path.isdir(os.path.join(c_dir, "GAMEPLAY")))
        self.assertTrue(os.path.isdir(os.path.join(c_dir, "IDEAS")))
        self.assertTrue(os.path.isdir(os.path.join(c_dir, "TURNS", "ACTIVE")))
        self.assertTrue(os.path.isdir(os.path.join(c_dir, "WORLD_FOUNDATION")))

        # Verify campaign_config.json
        cfg_path = os.path.join(c_dir, "campaign_config.json")
        self.assertTrue(os.path.isfile(cfg_path))
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg["id"], "test_stellar_voyage")
        self.assertEqual(cfg["operational_mode"], "classic_cyoa")

        # Verify status.json
        stat_path = os.path.join(c_dir, "GAMEPLAY", "status.json")
        self.assertTrue(os.path.isfile(stat_path))
        with open(stat_path, "r", encoding="utf-8") as f:
            stat = json.load(f)
        self.assertEqual(stat["campaign_id"], "test_stellar_voyage")
        self.assertEqual(stat["character"]["name"], "Commander Vane")
        self.assertEqual(stat["scene_anchor"]["location"], "Kepler Station Docking Bay 9")

        # Verify initial turn file
        turn1_path = os.path.join(c_dir, "TURNS", "ACTIVE", "turn_0001.md")
        self.assertTrue(os.path.isfile(turn1_path))
        with open(turn1_path, "r", encoding="utf-8") as f:
            t1 = f.read()
        self.assertIn("Kepler Station Docking Bay 9", t1)
        self.assertIn("Commander Vane", stat["character"]["name"])

    def test_consult_shadow_narrator(self):
        params = {
            "campaign_id": "test_shadow_camp",
            "title": "Shadow Realm",
            "protagonist_name": "Lyra",
            "location": "Midnight Spire"
        }
        scaffold_campaign(self.test_dir, params)

        advice = consult_shadow_narrator(self.test_dir, "test_shadow_camp", "Should I breach the locked gate?")
        self.assertEqual(advice["status"], "success")
        self.assertIn("Shadow Narrator Advisory", advice["advice"])
        self.assertIn("Midnight Spire", advice["advice"])

    def test_engine_init_campaign_endpoint(self):
        payload = json.dumps({
            "campaign_id": "server_scaffold_test",
            "title": "Server Test Campaign",
            "protagonist_name": "Unit Tester"
        }).encode("utf-8")

        status, headers, body = execute_request("POST", "/init_campaign", body=payload)
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["status"], "created")
        self.assertEqual(data["campaign_id"], "server_scaffold_test")

        # Clean up created test campaign in ROOT_DIR/CAMPAIGNS
        clean_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", "server_scaffold_test")
        if os.path.isdir(clean_dir):
            shutil.rmtree(clean_dir, ignore_errors=True)

    def test_engine_shadow_consult_endpoint(self):
        payload = json.dumps({
            "campaign": "template_campaign",
            "query": "Advise on upcoming conflict."
        }).encode("utf-8")

        status, headers, body = execute_request("POST", "/shadow/consult", body=payload)
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["status"], "success")
        self.assertIn("Shadow Narrator Advisory", data["advice"])


if __name__ == "__main__":
    unittest.main()
