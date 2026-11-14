#!/usr/bin/env python3
"""
ENGINE/calibration.py
=====================
Dynamic Agent Calibration Engine for Whimsy CYOA.
Analyzes rolling performance metrics over a window of recent turns (3-5 turns)
from telemetry and evaluation logs to detect recurring deficiencies (e.g.,
style contract violations, pacing escalation fatigue, tactical continuity drift).

Generates actionable CalibrationAdvisory text that is dynamically injected into
ENGINE/prompt_assembler.py so the Narrator and Shadow GM autonomously self-correct.
"""

import os
import json
from typing import Dict, Any, List, Optional

try:
    from ENGINE.telemetry import read_campaign_telemetry
except ImportError:
    from telemetry import read_campaign_telemetry

try:
    from ENGINE.evaluator import Evaluator, EvaluationReport
except ImportError:
    from evaluator import Evaluator, EvaluationReport


class CalibrationAdvisory:
    """Carries diagnostic health, identified deficiencies, and prompt directives."""
    def __init__(
        self,
        campaign_id: str,
        turns_analyzed: int,
        health_status: str,
        deficiencies: List[Dict[str, Any]],
        dimension_averages: Dict[str, float],
        advisory_prompt: str = ""
    ):
        self.campaign_id = campaign_id
        self.turns_analyzed = turns_analyzed
        self.health_status = health_status  # "healthy", "warning", "critical"
        self.deficiencies = deficiencies
        self.dimension_averages = {k: round(float(v), 2) for k, v in dimension_averages.items()}
        self.advisory_prompt = advisory_prompt

    def to_dict(self) -> Dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "turns_analyzed": self.turns_analyzed,
            "health_status": self.health_status,
            "deficiencies": self.deficiencies,
            "dimension_averages": self.dimension_averages,
            "advisory_prompt": self.advisory_prompt
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class CalibrationEngine:
    """Analyzes recent turns and generates calibration advisories."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.evaluator = Evaluator(root_dir)

    def analyze_campaign(
        self,
        campaign_id: str,
        window_size: int = 5,
        evaluation_reports: Optional[List[EvaluationReport]] = None
    ) -> CalibrationAdvisory:
        """
        Examines recent telemetry and evaluations across the rolling window.
        Identifies recurring deficiencies and builds dynamic advisory directives.
        """
        telemetry_records = read_campaign_telemetry(self.root_dir, campaign_id)
        recent_telemetry = telemetry_records[-window_size:] if telemetry_records else []

        # If explicit evaluation reports are not provided, synthesize or evaluate from active turns
        reports = evaluation_reports or []
        if not reports and recent_telemetry:
            # Check if telemetry has outcome or state deltas to estimate scores
            pass

        deficiencies: List[Dict[str, Any]] = []
        dimension_totals = {
            "world_grounding": 0.0,
            "tactical_continuity": 0.0,
            "pacing_alignment": 0.0,
            "style_contract_adherence": 0.0,
            "shadow_gm_steering": 0.0
        }
        dim_counts = {k: 0 for k in dimension_totals}

        # 1. Analyze Telemetry Trends
        style_violation_count = 0
        consecutive_high_intensity = 0
        max_consecutive_high_intensity = 0
        total_comp_tokens = 0

        for r in recent_telemetry:
            # Check style violations
            violations = r.get("style_violations", [])
            if violations:
                style_violation_count += len(violations)

            # Check pacing fatigue (consecutive intensity >= 4)
            intensity = r.get("narrative_intensity", 1)
            if intensity >= 4:
                consecutive_high_intensity += 1
                if consecutive_high_intensity > max_consecutive_high_intensity:
                    max_consecutive_high_intensity = consecutive_high_intensity
            else:
                consecutive_high_intensity = 0

            total_comp_tokens += r.get("completion_tokens", 0)

        # 2. Analyze Explicit Evaluation Reports if available
        if reports:
            for rep in reports:
                dscores = rep.dimension_scores if hasattr(rep, "dimension_scores") else rep.get("dimension_scores", {})
                for k, v in dscores.items():
                    if k in dimension_totals:
                        dimension_totals[k] += float(v)
                        dim_counts[k] += 1

        turns_count = max(len(recent_telemetry), len(reports))

        # Calculate dimension averages
        dimension_averages = {}
        for k in dimension_totals:
            if dim_counts[k] > 0:
                dimension_averages[k] = round(dimension_totals[k] / dim_counts[k], 2)
            else:
                # Default baseline score
                base = 4.5
                if k == "style_contract_adherence" and style_violation_count > 0:
                    base = max(1.0, 4.5 - (style_violation_count * 0.8))
                elif k == "pacing_alignment" and max_consecutive_high_intensity >= 3:
                    base = 2.5
                dimension_averages[k] = base

        # 3. Detect Specific Recurring Deficiencies
        # A. Style Drift
        if style_violation_count >= 2 or dimension_averages.get("style_contract_adherence", 5.0) < 3.0:
            deficiencies.append({
                "category": "style_drift",
                "severity": "high" if style_violation_count >= 3 else "medium",
                "description": f"Repeated style contract violations ({style_violation_count} recorded) across recent turns.",
                "directive": "CRITICAL STYLE DIRECTIVE: Cease all purple prose flourishes, decorative micro-SFX (e.g. sparks dancing, rumbling floors), and narrator praise. Anchor sentences in concrete, everyday vocabulary."
            })

        # B. Pacing Escalation Fatigue
        if max_consecutive_high_intensity >= 3 or dimension_averages.get("pacing_alignment", 5.0) < 3.0:
            deficiencies.append({
                "category": "pacing_fatigue",
                "severity": "medium",
                "description": f"High narrative intensity sustained for {max_consecutive_high_intensity} consecutive turns without dynamic decompression.",
                "directive": "PACING CALIBRATION: De-escalate scene tension. Shift focus to quiet sensory observations, tactical regrouping, or reflection before escalating to next climax."
            })

        # C. Tactical Continuity Drift
        if dimension_averages.get("tactical_continuity", 5.0) < 3.2:
            deficiencies.append({
                "category": "tactical_continuity",
                "severity": "high",
                "description": "Narrative outcomes frequently delay or omit direct resolution of player action.",
                "directive": "TACTICAL CONTINUITY MANDATE: The player's specific stated action must be causally resolved in the immediate first sentence of the GM response."
            })

        # D. World Grounding Drift
        if dimension_averages.get("world_grounding", 5.0) < 3.2:
            deficiencies.append({
                "category": "world_grounding",
                "severity": "high",
                "description": "Setting descriptions lack concrete grounding in World Bible facts or risk epistemic horizon leaks.",
                "directive": "GROUNDING DIRECTIVE: Explicitly anchor scenes to established campaign locations, factions, and strict NPC knowledge limits."
            })

        # Determine overall health status
        health_status = "healthy"
        if any(d["severity"] == "high" for d in deficiencies) or len(deficiencies) >= 2:
            health_status = "critical" if any(d["severity"] == "high" for d in deficiencies) and len(deficiencies) >= 2 else "warning"
        elif deficiencies:
            health_status = "warning"

        # Generate combined advisory prompt text
        advisory_lines = []
        if deficiencies:
            advisory_lines.append("=== DYNAMIC AGENT CALIBRATION ADVISORY ===")
            advisory_lines.append(f"Status: {health_status.upper()} | Rolling Window: {turns_count} turns analyzed")
            advisory_lines.append("Self-correction directives based on detected deficiencies:")
            for d in deficiencies:
                advisory_lines.append(f"- [{d['category'].upper()}] {d['directive']}")
            advisory_lines.append("Ensure your turn response incorporates these corrections immediately.")

        advisory_prompt = "\n".join(advisory_lines)

        return CalibrationAdvisory(
            campaign_id=campaign_id,
            turns_analyzed=turns_count,
            health_status=health_status,
            deficiencies=deficiencies,
            dimension_averages=dimension_averages,
            advisory_prompt=advisory_prompt
        )


def get_calibration_advisory(
    root_dir: str,
    campaign_id: str,
    window_size: int = 5,
    evaluation_reports: Optional[List[EvaluationReport]] = None
) -> CalibrationAdvisory:
    """Helper function to analyze campaign calibration and retrieve advisory."""
    engine = CalibrationEngine(root_dir)
    return engine.analyze_campaign(campaign_id, window_size, evaluation_reports)
