#!/usr/bin/env python3
"""
Unit tests for ENGINE/calibration.py and dynamic prompt injection.
Verifies:
1. Rolling window score and telemetry analysis across turns.
2. Recurring deficiency detection (style drift, pacing escalation fatigue, tactical drift).
3. CalibrationAdvisory generation with actionable self-correction directives.
4. Dynamic prompt injection into PromptAssembler system prompt.
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

from ENGINE.telemetry import record_turn_telemetry
from ENGINE.calibration import CalibrationEngine, get_calibration_advisory, CalibrationAdvisory
from ENGINE.prompt_assembler import PromptAssembler, assemble_prompt
from ENGINE.evaluator import EvaluationReport


class TestCalibration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.campaign_id = "calibration_test_campaign"
        self.gameplay_dir = os.path.join(self.test_dir, "CAMPAIGNS", self.campaign_id, "GAMEPLAY")
        os.makedirs(self.gameplay_dir, exist_ok=True)
        # Create minimal status.json
        status_data = {
            "campaign_id": self.campaign_id,
            "turn": 5,
            "operational_mode": "classic_cyoa",
            "pacing_state": {"zoom_level": "detailed_scene", "narrative_intensity": 2}
        }
        with open(os.path.join(self.gameplay_dir, "status.json"), "w", encoding="utf-8") as f:
            json.dump(status_data, f)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_healthy_campaign_advisory(self):
        """Verifies that optimal telemetry and evaluations produce a healthy status and empty advisory prompt."""
        # Log 5 clean turns
        for turn in range(1, 6):
            record_turn_telemetry(
                root_dir=self.test_dir,
                campaign_id=self.campaign_id,
                turn=turn,
                latency_ms=120.0,
                model="test-model",
                operational_mode="classic_cyoa",
                zoom_level="detailed_scene",
                narrative_intensity=2,
                prompt_tokens=400,
                completion_tokens=150,
                retrieval_hits=2,
                style_violations=[],
                outcome_state_delta={}
            )

        advisory = get_calibration_advisory(self.test_dir, self.campaign_id, window_size=5)
        self.assertEqual(advisory.health_status, "healthy")
        self.assertEqual(len(advisory.deficiencies), 0)
        self.assertEqual(advisory.advisory_prompt, "")
        self.assertEqual(advisory.turns_analyzed, 5)

    def test_detect_style_drift_deficiency(self):
        """Verifies detection of recurring style violations across the rolling window."""
        # Log turns with recurring style contract violations
        for turn in range(1, 4):
            record_turn_telemetry(
                root_dir=self.test_dir,
                campaign_id=self.campaign_id,
                turn=turn,
                latency_ms=150.0,
                model="test-model",
                operational_mode="classic_cyoa",
                zoom_level="detailed_scene",
                narrative_intensity=2,
                prompt_tokens=400,
                completion_tokens=150,
                retrieval_hits=1,
                style_violations=["Decorative micro-SFX: 'sparks danced'"],
                outcome_state_delta={}
            )

        advisory = get_calibration_advisory(self.test_dir, self.campaign_id, window_size=3)
        self.assertIn(advisory.health_status, ["warning", "critical"])
        categories = [d["category"] for d in advisory.deficiencies]
        self.assertIn("style_drift", categories)
        self.assertIn("CRITICAL STYLE DIRECTIVE", advisory.advisory_prompt)
        self.assertIn("DYNAMIC AGENT CALIBRATION ADVISORY", advisory.advisory_prompt)

    def test_detect_pacing_escalation_fatigue(self):
        """Verifies detection of high narrative intensity sustained across 3+ consecutive turns."""
        for turn in range(1, 5):
            record_turn_telemetry(
                root_dir=self.test_dir,
                campaign_id=self.campaign_id,
                turn=turn,
                latency_ms=140.0,
                model="test-model",
                operational_mode="classic_cyoa",
                zoom_level="detailed_scene",
                narrative_intensity=5,  # Peak intensity
                prompt_tokens=400,
                completion_tokens=180,
                retrieval_hits=1,
                style_violations=[],
                outcome_state_delta={}
            )

        advisory = get_calibration_advisory(self.test_dir, self.campaign_id, window_size=4)
        self.assertIn(advisory.health_status, ["warning", "critical"])
        categories = [d["category"] for d in advisory.deficiencies]
        self.assertIn("pacing_fatigue", categories)
        self.assertIn("PACING CALIBRATION", advisory.advisory_prompt)

    def test_rolling_evaluation_reports_analysis(self):
        """Verifies that explicit low evaluation reports trigger tactical and grounding directives."""
        rep1 = EvaluationReport(
            turn_num=1,
            campaign_id=self.campaign_id,
            overall_score=2.2,
            dimension_scores={
                "world_grounding": 2.5,
                "tactical_continuity": 2.0,
                "pacing_alignment": 3.0,
                "style_contract_adherence": 3.0,
                "shadow_gm_steering": 3.0
            },
            evidence={},
            critique={},
            remedy={},
            bias_adjustments={}
        )
        rep2 = EvaluationReport(
            turn_num=2,
            campaign_id=self.campaign_id,
            overall_score=2.4,
            dimension_scores={
                "world_grounding": 2.8,
                "tactical_continuity": 2.2,
                "pacing_alignment": 3.5,
                "style_contract_adherence": 3.5,
                "shadow_gm_steering": 3.0
            },
            evidence={},
            critique={},
            remedy={},
            bias_adjustments={}
        )

        engine = CalibrationEngine(self.test_dir)
        advisory = engine.analyze_campaign(self.campaign_id, window_size=2, evaluation_reports=[rep1, rep2])

        self.assertIn(advisory.health_status, ["warning", "critical"])
        categories = [d["category"] for d in advisory.deficiencies]
        self.assertIn("tactical_continuity", categories)
        self.assertIn("world_grounding", categories)
        self.assertIn("TACTICAL CONTINUITY MANDATE", advisory.advisory_prompt)
        self.assertIn("GROUNDING DIRECTIVE", advisory.advisory_prompt)

    def test_dynamic_prompt_injection(self):
        """Verifies that PromptAssembler injects dynamic calibration advisories when present."""
        assembler = PromptAssembler(ROOT_DIR)

        # 1. Custom advisory passed explicitly
        custom_advisory = "- [STYLE_DRIFT] Eliminate narrator praise immediately."
        prompt = assembler.build_system_prompt("template_campaign", calibration_advisory=custom_advisory)

        self.assertIn("# 1.1 DYNAMIC AGENT CALIBRATION ADVISORY (SELF-CORRECTION DIRECTIVES)", prompt)
        self.assertIn(custom_advisory, prompt)

        # 2. When empty string passed, section is suppressed
        clean_prompt = assembler.build_system_prompt("template_campaign", calibration_advisory="")
        self.assertNotIn("# 1.1 DYNAMIC AGENT CALIBRATION ADVISORY", clean_prompt)


if __name__ == "__main__":
    unittest.main()
