#!/usr/bin/env python3
"""
Unit tests for ENGINE/evaluator.py.
Verifies:
1. Standardized rubric schema validation and structural conformity.
2. Direct multi-dimensional scoring calculation across the 5 dimensions.
3. Structured evidence citation, critique, and remedy generation.
4. Bias mitigation (length bias verbosity penalty and position bias checks).
"""

import os
import sys
import json
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.evaluator import Evaluator, EvaluationReport
from tests.test_schemas import SimpleSchemaValidator


class TestEvaluator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluator = Evaluator(ROOT_DIR)
        cls.schema_path = os.path.join(ROOT_DIR, "GLOBAL", "SCHEMAS", "evaluation_rubric.schema.json")
        cls.rubric_path = os.path.join(ROOT_DIR, "GLOBAL", "RUBRICS", "narrator_evaluation_rubric.json")

    def test_rubric_schema_conformity(self):
        """Verifies narrator_evaluation_rubric.json validates strictly against evaluation_rubric.schema.json."""
        with open(self.schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        with open(self.rubric_path, "r", encoding="utf-8") as f:
            rubric = json.load(f)

        errors = SimpleSchemaValidator.validate(rubric, schema)
        self.assertEqual(errors, [], f"Evaluation rubric schema validation errors: {errors}")
        self.assertEqual(rubric["rubric_id"], "narrator_turn_evaluation_v1")

        # Verify all 5 required dimensions
        dim_ids = [d["id"] for d in rubric["dimensions"]]
        expected_dims = [
            "world_grounding",
            "tactical_continuity",
            "pacing_alignment",
            "style_contract_adherence",
            "shadow_gm_steering"
        ]
        for ed in expected_dims:
            self.assertIn(ed, dim_ids, f"Missing required dimension {ed}")

        # Verify weights sum to 1.0 (approx)
        total_weight = sum(d["weight"] for d in rubric["dimensions"])
        self.assertAlmostEqual(total_weight, 1.0, places=2)

        # Verify score anchors for 1, 3, 5
        for d in rubric["dimensions"]:
            anchors = d["score_anchors"]
            self.assertIn("1", anchors)
            self.assertIn("3", anchors)
            self.assertIn("5", anchors)

    def test_direct_scoring_exemplary_turn(self):
        """Verifies high scores and evidence citation for an exemplary grounded turn."""
        action = "Inspect the rusted console for power cables"
        response = (
            "You inspect the rusted console for power cables, gently peeling away oxidized casing. "
            "Beneath the oxidized metal, twin insulated copper conduits run toward the main terminal door. "
            "The air in the sector remains cold and still, save for the faint hum of emergency relays.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Splice into the left conduit with your wire cutters.\n"
            "2. Trace the right conduit toward the ventilation shaft.\n"
            "3. Step back and confer with your team.\n"
            "4. Monitor the terminal screen for incoming signal alerts.\n\n"
            "[SYS: Turn 2 | Energy: 100/100 | Checkpoints: 5/5]"
        )

        context = {
            "known_entities": {"console", "copper conduits", "terminal door"},
            "canon_secrets": ["Project Prometheus secret reactor"],
            "zoom_level": "detailed_scene",
            "narrative_intensity": 2
        }

        report = self.evaluator.evaluate_turn(
            campaign_id="template_campaign",
            turn_num=1,
            action=action,
            response=response,
            context=context
        )

        self.assertIsInstance(report, EvaluationReport)
        self.assertGreaterEqual(report.overall_score, 4.0)
        self.assertEqual(report.dimension_scores["tactical_continuity"], 5.0)
        self.assertEqual(report.dimension_scores["style_contract_adherence"], 5.0)
        self.assertEqual(report.dimension_scores["shadow_gm_steering"], 5.0)

        # Check evidence citations
        self.assertTrue(len(report.evidence["tactical_continuity"]) > 0)
        self.assertIn("Immediate causal reaction", report.evidence["tactical_continuity"][0])
        self.assertTrue(len(report.critique["tactical_continuity"]) > 0)
        self.assertTrue(len(report.remedy["tactical_continuity"]) > 0)

    def test_tactical_continuity_penalty_on_unrelated_response(self):
        """Verifies tactical_continuity score drops when response ignores player action."""
        action = "Examine the locked bulkhead"
        unrelated_response = (
            "Far across the valley, a flock of birds scatters into the sunset clouds. "
            "You wonder what tomorrow's weather will bring.\n\n"
            "1. Sleep.\n2. Eat."
        )

        report = self.evaluator.evaluate_turn(
            campaign_id="template_campaign",
            turn_num=1,
            action=action,
            response=unrelated_response
        )

        self.assertLess(report.dimension_scores["tactical_continuity"], 3.0)
        self.assertTrue(any("lacked explicit causal echoes" in ev for ev in report.evidence["tactical_continuity"]))

    def test_style_contract_adherence_scoring(self):
        """Verifies penalties for purple prose, STEM jargon, and narrator praise."""
        action = "Attack the guard"
        prose_with_violations = (
            "You attack the guard with breathtaking prowess, your sheer brilliance leaving him stunned! "
            "Elemental energy sparking off your fork, you calculate the differential equation of the deceleration multiplier.\n\n"
            "1. Retreat.\n2. Advance."
        )

        report = self.evaluator.evaluate_turn(
            campaign_id="template_campaign",
            turn_num=1,
            action=action,
            response=prose_with_violations
        )

        # Violations: narrator praise, STEM jargon, decorative micro-SFX
        self.assertLessEqual(report.dimension_scores["style_contract_adherence"], 2.5)
        self.assertTrue(len(report.evidence["style_contract_adherence"]) > 0)

    def test_world_grounding_canon_secret_leak_penalty(self):
        """Verifies severe penalty when hidden canon secrets leak unearned to the protagonist."""
        action = "Search the filing cabinet"
        leaked_secret = "The Archon is secretly a synthetic construct operating from Orbit-7"
        response = (
            f"You search the cabinet and suddenly realize: {leaked_secret}!\n\n"
            "1. Keep searching.\n2. Leave."
        )

        context = {
            "known_entities": set(),
            "canon_secrets": [leaked_secret],
            "zoom_level": "detailed_scene"
        }

        report = self.evaluator.evaluate_turn(
            campaign_id="template_campaign",
            turn_num=1,
            action=action,
            response=response,
            context=context
        )

        self.assertEqual(report.dimension_scores["world_grounding"], 1.0)
        self.assertTrue(any("Canon secret exposed" in ev for ev in report.evidence["world_grounding"]))

    def test_length_bias_mitigation_penalizes_low_substance_verbosity(self):
        """Verifies that an excessively verbose response with low substance density is penalized."""
        action = "Look around"
        # 600+ words of repetitive purple descriptions with no concrete tactical substance
        fluff_paragraph = "The mysterious ethereal vapor floated endlessly across the ancient misty expanse. " * 60
        response = f"You look around. {fluff_paragraph}\n\n1. Move forward.\n2. Stand still."

        report = self.evaluator.evaluate_turn(
            campaign_id="template_campaign",
            turn_num=1,
            action=action,
            response=response
        )

        length_bias = report.bias_adjustments["length_bias"]
        self.assertTrue(length_bias["length_bias_detected"])
        self.assertGreater(length_bias["length_penalty"], 0.0)
        self.assertIn("Verbosity penalty applied", length_bias["explanation"])

    def test_position_bias_mitigation_checks_option_balance(self):
        """Verifies position skew check when Option 1 excessively dominates choices."""
        action = "Choose path"
        # Option 1 has 30 words, Options 2-4 have 3 words each
        skewed_response = (
            "You choose your next move carefully.\n\n"
            "1. Proceed down the western corridor with extreme caution, checking every tile for pressure plates while keeping your weapon drawn and eyes focused.\n"
            "2. Turn left.\n"
            "3. Wait here.\n"
            "4. Go back."
        )

        report = self.evaluator.evaluate_turn(
            campaign_id="template_campaign",
            turn_num=1,
            action=action,
            response=skewed_response
        )

        pos_bias = report.bias_adjustments["position_bias"]
        self.assertTrue(pos_bias["order_invariant"])
        self.assertLess(pos_bias["choice_balance_score"], 1.0)
        self.assertIn("Position skew detected", pos_bias["explanation"])


if __name__ == "__main__":
    unittest.main()
