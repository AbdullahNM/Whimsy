#!/usr/bin/env python3
"""
Unit and integration tests for operational mode separation and deterministic action validation.
Tests:
- Classic CYOA mode action validation (rejects freeform, compound, out-of-range; accepts valid options)
- Freeform simulation mode action validation (accepts prose, compound; rejects empty)
- Mode configuration persistence and schema compatibility
- HTTP /generate endpoint validation enforcement (HTTP 400 on invalid actions, state immutability)
"""

import os
import sys
import json
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.mode_validator import (
    validate_action,
    get_campaign_mode,
    extract_offered_choices,
    extract_options_from_text,
    DEFAULT_FALLBACK_CHOICES
)
from tests.test_engine_server import execute_request
from tests.test_schemas import SimpleSchemaValidator


class TestModeValidator(unittest.TestCase):
    def setUp(self):
        self.campaign_id = "template_campaign"
        self.choices = extract_offered_choices(self.campaign_id, ROOT_DIR)
        self.assertTrue(len(self.choices) >= 3, "Template campaign should offer at least 3 choices")

    # -------------------------------------------------------------------------
    # Classic CYOA Mode: Rejections
    # -------------------------------------------------------------------------

    def test_classic_mode_rejects_freeform_actions(self):
        """Classic mode must reject arbitrary freeform actions."""
        freeform_actions = [
            "I want to sneak past the front guards",
            "jump out the window into the canal",
            "search Handler Cross's office desk",
            "Accept the contract and head to the staging bay",
            "look around the perimeter",
            "hack into the terminal database"
        ]
        for action in freeform_actions:
            is_valid, error_msg, parsed = validate_action(
                action=action,
                mode="classic_cyoa",
                campaign_id=self.campaign_id,
                root_dir=ROOT_DIR
            )
            self.assertFalse(is_valid, f"Expected {action!r} to be rejected in classic_cyoa")
            self.assertTrue(len(error_msg) > 0, "Error message should not be empty")
            self.assertEqual(parsed, {}, "Parsed action should be empty dict on validation failure")

    def test_classic_mode_rejects_compound_actions(self):
        """Classic mode must reject compound or chained actions."""
        compound_actions = [
            "1 and then search",
            "1, 2",
            "1 and 2",
            "1 & 2",
            "1 then 2",
            "Option 1 and Option 2",
            "Option 1, Option 2",
            "1, 2, 3",
            "1 then search the room",
            "1, look for hidden clues",
            "1; take cover behind the pillar",
            "1 and inspect the terminal",
            "Option 1 and then run"
        ]
        for action in compound_actions:
            is_valid, error_msg, parsed = validate_action(
                action=action,
                mode="classic_cyoa",
                campaign_id=self.campaign_id,
                root_dir=ROOT_DIR
            )
            self.assertFalse(is_valid, f"Expected compound action {action!r} to be rejected")
            self.assertIn("Compound", error_msg)
            self.assertEqual(parsed, {})

    def test_classic_mode_rejects_out_of_range_options(self):
        """Classic mode must reject numbers outside the offered option range."""
        out_of_range = ["0", "4", "5", "99", "Option 0", "Option 5", "Option 99", "-1", "-2"]
        for action in out_of_range:
            is_valid, error_msg, parsed = validate_action(
                action=action,
                mode="classic_cyoa",
                campaign_id=self.campaign_id,
                root_dir=ROOT_DIR
            )
            self.assertFalse(is_valid, f"Expected out-of-range action {action!r} to be rejected")
            self.assertIn("out of range", error_msg.lower())
            self.assertEqual(parsed, {})

    def test_classic_mode_rejects_empty_action(self):
        """Classic mode must reject empty or whitespace-only actions."""
        for action in ["", "   ", "\t", "\n", None]:
            is_valid, error_msg, parsed = validate_action(
                action=action,
                mode="classic_cyoa",
                campaign_id=self.campaign_id,
                root_dir=ROOT_DIR
            )
            self.assertFalse(is_valid)
            self.assertIn("empty", error_msg.lower())
            self.assertEqual(parsed, {})

    # -------------------------------------------------------------------------
    # Classic CYOA Mode: Acceptances
    # -------------------------------------------------------------------------

    def test_classic_mode_accepts_exact_option_index(self):
        """Classic mode must accept single exact indices in varied valid notations."""
        valid_inputs = [
            ("1", 1),
            (" 1 ", 1),
            ("2", 2),
            ("3", 3),
            ("Option 1", 1),
            ("option 2", 2),
            ("OPTION 3", 3),
            ("Choice 1", 1),
            ("choice 2", 2),
            ("CHOICE 3", 3),
            ("1.", 1),
            ("2)", 2),
            ("Option 1.", 1),
            ("Choice 2)", 2)
        ]
        for action, expected_idx in valid_inputs:
            is_valid, error_msg, parsed = validate_action(
                action=action,
                mode="classic_cyoa",
                campaign_id=self.campaign_id,
                root_dir=ROOT_DIR
            )
            self.assertTrue(is_valid, f"Expected action {action!r} to be accepted (err: {error_msg})")
            self.assertEqual(error_msg, "")
            self.assertEqual(parsed.get("index"), expected_idx)
            self.assertEqual(parsed.get("mode"), "classic_cyoa")
            self.assertIn("text", parsed)

    def test_classic_mode_accepts_option_with_text(self):
        """Classic mode must accept option index followed by offered option text or exact text."""
        # Full text from turn_0001
        opt1_text = self.choices[0]["text"]
        full_line = f"1. {opt1_text}"
        is_valid, error_msg, parsed = validate_action(
            action=full_line,
            mode="classic_cyoa",
            campaign_id=self.campaign_id,
            root_dir=ROOT_DIR
        )
        self.assertTrue(is_valid, f"Failed on full line option: {error_msg}")
        self.assertEqual(parsed.get("index"), 1)

        # Exact option text without number
        is_valid, error_msg, parsed = validate_action(
            action=opt1_text,
            mode="classic_cyoa",
            campaign_id=self.campaign_id,
            root_dir=ROOT_DIR
        )
        self.assertTrue(is_valid, f"Failed on option text: {error_msg}")
        self.assertEqual(parsed.get("index"), 1)

        # Title portion only
        title_only = "Accept Contract Alpha"
        is_valid, error_msg, parsed = validate_action(
            action=title_only,
            mode="classic_cyoa",
            campaign_id=self.campaign_id,
            root_dir=ROOT_DIR
        )
        self.assertTrue(is_valid, f"Failed on option title: {error_msg}")
        self.assertEqual(parsed.get("index"), 1)

    # -------------------------------------------------------------------------
    # Freeform Simulation Mode
    # -------------------------------------------------------------------------

    def test_freeform_mode_accepts_compound_and_prose(self):
        """Freeform mode must permit compound actions, chained verbs, and arbitrary prose."""
        freeform_samples = [
            "1 and then search",
            "1, 2",
            "Sneak past the surveillance camera and hack the maintenance console",
            "I draw my sidearm and whisper into the comms for Handler Cross",
            "Accept contract alpha, but first delay 5 minutes to run diagnostics",
            "Search the desk, examine the locked terminal, and then open the window"
        ]
        for action in freeform_samples:
            is_valid, error_msg, parsed = validate_action(
                action=action,
                mode="freeform_simulation",
                campaign_id=self.campaign_id,
                root_dir=ROOT_DIR
            )
            self.assertTrue(is_valid, f"Expected freeform action {action!r} to be valid: {error_msg}")
            self.assertEqual(error_msg, "")
            self.assertEqual(parsed.get("mode"), "freeform_simulation")
            self.assertEqual(parsed.get("index"), None)
            self.assertEqual(parsed.get("text"), action.strip())

    def test_freeform_mode_rejects_empty_action(self):
        """Freeform mode must reject empty or whitespace-only input."""
        for action in ["", "   ", "\t", None]:
            is_valid, error_msg, parsed = validate_action(
                action=action,
                mode="freeform_simulation",
                campaign_id=self.campaign_id,
                root_dir=ROOT_DIR
            )
            self.assertFalse(is_valid)
            self.assertIn("empty", error_msg.lower())
            self.assertEqual(parsed, {})

    # -------------------------------------------------------------------------
    # Mode Persistence & Schema
    # -------------------------------------------------------------------------

    def test_campaign_config_operational_mode_persistence(self):
        """Verify campaign_config.json persists operational_mode and validates against schema."""
        cfg_path = os.path.join(ROOT_DIR, "CAMPAIGNS", self.campaign_id, "campaign_config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.assertIn("operational_mode", cfg)
        self.assertEqual(cfg["operational_mode"], "classic_cyoa")

        # Validate against campaign_init.schema.json
        schema_path = os.path.join(ROOT_DIR, "GLOBAL", "SCHEMAS", "campaign_init.schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        errors = SimpleSchemaValidator.validate(cfg, schema)
        self.assertEqual(errors, [], f"Schema validation errors: {errors}")

        # Invalid operational_mode must fail schema validation
        bad_cfg = dict(cfg)
        bad_cfg["operational_mode"] = "invalid_arcade_mode"
        bad_errors = SimpleSchemaValidator.validate(bad_cfg, schema)
        self.assertTrue(any("not in enum" in e for e in bad_errors))

    def test_get_campaign_mode_resolution(self):
        """get_campaign_mode should correctly resolve modes and default to classic_cyoa."""
        self.assertEqual(get_campaign_mode("template_campaign", ROOT_DIR), "classic_cyoa")
        self.assertEqual(get_campaign_mode("nonexistent_campaign", ROOT_DIR), "classic_cyoa")
        self.assertEqual(get_campaign_mode("", ROOT_DIR), "classic_cyoa")

    def test_extract_offered_choices_fallback(self):
        """Choices extraction should fallback to default standard choices when none found."""
        fallback = extract_offered_choices("nonexistent_campaign", ROOT_DIR)
        self.assertEqual(len(fallback), len(DEFAULT_FALLBACK_CHOICES))
        self.assertEqual(fallback[0]["index"], 1)


class TestEngineModeIntegration(unittest.TestCase):
    """Integration tests verifying HTTP /generate enforces deterministic action validation."""

    def test_http_generate_rejects_invalid_classic_action_with_400(self):
        """POST /generate on a classic campaign must return HTTP 400 for freeform actions."""
        payload = {
            "action": "I attempt to hack the defense mainframe",
            "campaign": "template_campaign",
            "pacing": "standard",
            "currentTurn": 1
        }
        status, headers, resp_body = execute_request(
            "POST",
            "/generate",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 400)
        self.assertEqual(headers.get("access-control-allow-origin"), "*")
        data = json.loads(resp_body.decode("utf-8"))
        self.assertEqual(data.get("error"), "INVALID_ACTION")
        self.assertEqual(data.get("mode"), "classic_cyoa")
        self.assertTrue(len(data.get("message", "")) > 0)

    def test_http_generate_rejects_compound_action_with_400(self):
        """POST /generate on classic campaign must return HTTP 400 for compound actions."""
        payload = {
            "action": "1 and then search the bodies",
            "campaign": "template_campaign",
            "currentTurn": 1
        }
        status, headers, resp_body = execute_request(
            "POST",
            "/generate",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 400)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertEqual(data.get("error"), "INVALID_ACTION")
        self.assertIn("Compound", data.get("message", ""))

    def test_http_generate_rejects_out_of_range_with_400(self):
        """POST /generate on classic campaign must return HTTP 400 for out-of-range option indices."""
        payload = {
            "action": "99",
            "campaign": "template_campaign",
            "currentTurn": 1
        }
        status, headers, resp_body = execute_request(
            "POST",
            "/generate",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 400)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertEqual(data.get("error"), "INVALID_ACTION")
        self.assertIn("out of range", data.get("message", "").lower())

    def test_http_generate_immutability_on_failure(self):
        """Validation failure must ensure NO state or turn files are created or modified."""
        active_turns_dir = os.path.join(ROOT_DIR, "CAMPAIGNS", "template_campaign", "TURNS", "ACTIVE")
        files_before = os.listdir(active_turns_dir)
        mtimes_before = {f: os.path.getmtime(os.path.join(active_turns_dir, f)) for f in files_before}

        status_path = os.path.join(ROOT_DIR, "CAMPAIGNS", "template_campaign", "GAMEPLAY", "status.json")
        status_mtime_before = os.path.getmtime(status_path)

        # Trigger invalid action
        payload = {
            "action": "Invalid freeform action that should not touch disk",
            "campaign": "template_campaign",
            "currentTurn": 1
        }
        status, _, _ = execute_request(
            "POST",
            "/generate",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 400)

        # Verify disk immutability
        files_after = os.listdir(active_turns_dir)
        self.assertEqual(files_before, files_after, "Active turns directory files should not change")
        for f in files_before:
            self.assertEqual(
                mtimes_before[f],
                os.path.getmtime(os.path.join(active_turns_dir, f)),
                f"File {f} mtime should be unchanged"
            )

        status_mtime_after = os.path.getmtime(status_path)
        self.assertEqual(status_mtime_before, status_mtime_after, "status.json mtime should be unchanged")

    def test_http_generate_accepts_valid_classic_action(self):
        """POST /generate on classic campaign must return HTTP 200 for valid choice."""
        payload = {
            "action": "1",
            "campaign": "template_campaign",
            "currentTurn": 1
        }
        status, headers, resp_body = execute_request(
            "POST",
            "/generate",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 200)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertIn("response", data)

    def test_http_generate_accepts_freeform_when_configured(self):
        """POST /generate must accept freeform/compound actions when operational_mode is freeform_simulation."""
        payload = {
            "action": "1 and then search the back alley for clues",
            "campaign": "template_campaign",
            "operational_mode": "freeform_simulation",
            "currentTurn": 1
        }
        status, headers, resp_body = execute_request(
            "POST",
            "/generate",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(status, 200)
        data = json.loads(resp_body.decode("utf-8"))
        self.assertIn("response", data)


if __name__ == "__main__":
    unittest.main()
