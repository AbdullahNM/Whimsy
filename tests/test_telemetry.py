#!/usr/bin/env python3
"""
Unit tests for ENGINE/telemetry.py.
Verifies:
1. Structured JSONL event logging and file persistence.
2. Telemetry record schema conformity and validation error handling.
3. Aggregate summary calculation (averages, token budgets, pacing distribution, style frequency).
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

from ENGINE.telemetry import (
    record_turn_telemetry,
    read_campaign_telemetry,
    get_campaign_telemetry_summary,
    validate_telemetry_record,
    REQUIRED_TELEMETRY_FIELDS
)


class TestTelemetry(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.campaign_id = "telemetry_test_campaign"
        self.gameplay_dir = os.path.join(self.test_dir, "CAMPAIGNS", self.campaign_id, "GAMEPLAY")
        os.makedirs(self.gameplay_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_schema_field_requirements(self):
        """Verifies that validate_telemetry_record catches missing required fields."""
        incomplete_record = {
            "timestamp": "2026-11-14T12:00:00Z",
            "campaign_id": self.campaign_id,
            "turn": 1
        }
        errors = validate_telemetry_record(incomplete_record)
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("latency_ms" in err for err in errors))
        self.assertTrue(any("outcome_state_delta" in err for err in errors))

    def test_schema_field_type_validation(self):
        """Verifies type checking for intensity, tokens, and latency."""
        invalid_record = {
            "timestamp": "2026-11-14T12:00:00Z",
            "campaign_id": self.campaign_id,
            "turn": "one",  # Should be int
            "latency_ms": "fast",  # Should be number
            "model": "test-model",
            "operational_mode": "classic_cyoa",
            "zoom_level": "detailed_scene",
            "narrative_intensity": 7,  # Out of 1-5 range
            "prompt_tokens": "zero",  # Should be int
            "completion_tokens": 100,
            "retrieval_hits": 2,
            "style_violations": "none",  # Should be list
            "outcome_state_delta": []  # Should be dict
        }
        errors = validate_telemetry_record(invalid_record)
        self.assertGreaterEqual(len(errors), 5)
        self.assertTrue(any("narrative_intensity" in err for err in errors))
        self.assertTrue(any("style_violations" in err for err in errors))

    def test_record_turn_telemetry_persists_valid_jsonl(self):
        """Verifies that record_turn_telemetry writes valid JSONL lines conforming to schema."""
        rec1 = record_turn_telemetry(
            root_dir=self.test_dir,
            campaign_id=self.campaign_id,
            turn=1,
            latency_ms=152.4,
            model="gemini-2.5-flash",
            operational_mode="classic_cyoa",
            zoom_level="detailed_scene",
            narrative_intensity=2,
            prompt_tokens=450,
            completion_tokens=180,
            retrieval_hits=3,
            style_violations=[],
            outcome_state_delta={"hp": 100}
        )
        self.assertIn("timestamp", rec1)
        self.assertEqual(rec1["turn"], 1)
        self.assertEqual(rec1["latency_ms"], 152.4)

        rec2 = record_turn_telemetry(
            root_dir=self.test_dir,
            campaign_id=self.campaign_id,
            turn=2,
            latency_ms=210.8,
            model="gemini-2.5-flash",
            operational_mode="classic_cyoa",
            zoom_level="short_summary",
            narrative_intensity=3,
            prompt_tokens=520,
            completion_tokens=220,
            retrieval_hits=1,
            style_violations=["Decorative micro-SFX detected: 'sparks danced'"],
            outcome_state_delta={"hp": 95}
        )
        self.assertEqual(rec2["turn"], 2)

        records = read_campaign_telemetry(self.test_dir, self.campaign_id)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["turn"], 1)
        self.assertEqual(records[1]["turn"], 2)
        self.assertEqual(len(records[1]["style_violations"]), 1)

    def test_summary_aggregation_empty_log(self):
        """Verifies safe empty defaults when no telemetry exists."""
        summary = get_campaign_telemetry_summary(self.test_dir, "nonexistent_campaign")
        self.assertEqual(summary["total_turns"], 0)
        self.assertEqual(summary["avg_latency_ms"], 0.0)
        self.assertEqual(summary["token_budgets"]["avg_prompt_tokens"], 0.0)
        self.assertEqual(summary["style_violation_frequency"]["total_violations"], 0)

    def test_summary_aggregation_calculations(self):
        """Verifies correct statistical aggregation across multiple turns."""
        turns_data = [
            (1, 100.0, "detailed_scene", 2, 400, 100, []),
            (2, 200.0, "detailed_scene", 4, 600, 200, ["Prohibited STEM: 'lambda'"]),
            (3, 300.0, "montage", 3, 500, 150, []),
            (4, 400.0, "time_skip", 1, 500, 150, ["Prohibited STEM: 'reynolds quotient'", "Praise"])
        ]

        for turn, lat, zoom, intensity, p_tok, c_tok, viols in turns_data:
            record_turn_telemetry(
                root_dir=self.test_dir,
                campaign_id=self.campaign_id,
                turn=turn,
                latency_ms=lat,
                model="test-model",
                operational_mode="classic_cyoa",
                zoom_level=zoom,
                narrative_intensity=intensity,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                retrieval_hits=1,
                style_violations=viols,
                outcome_state_delta={}
            )

        summary = get_campaign_telemetry_summary(self.test_dir, self.campaign_id)

        self.assertEqual(summary["total_turns"], 4)
        # Avg latency: (100 + 200 + 300 + 400) / 4 = 250.0
        self.assertEqual(summary["avg_latency_ms"], 250.0)

        # Token budgets
        self.assertEqual(summary["token_budgets"]["total_prompt_tokens"], 2000)
        self.assertEqual(summary["token_budgets"]["avg_prompt_tokens"], 500.0)
        self.assertEqual(summary["token_budgets"]["total_completion_tokens"], 600)
        self.assertEqual(summary["token_budgets"]["avg_completion_tokens"], 150.0)

        # Pacing distribution
        pacing = summary["pacing_distribution"]
        # Avg intensity: (2 + 4 + 3 + 1) / 4 = 2.5
        self.assertEqual(pacing["avg_narrative_intensity"], 2.5)
        self.assertEqual(pacing["zoom_levels"]["detailed_scene"]["count"], 2)
        self.assertEqual(pacing["zoom_levels"]["detailed_scene"]["percentage"], 50.0)
        self.assertEqual(pacing["zoom_levels"]["montage"]["count"], 1)
        self.assertEqual(pacing["zoom_levels"]["time_skip"]["count"], 1)

        # Style violations
        style = summary["style_violation_frequency"]
        self.assertEqual(style["total_violations"], 3)
        self.assertEqual(style["turns_with_violations"], 2)
        self.assertEqual(style["violation_rate"], 0.75)


if __name__ == "__main__":
    unittest.main()
