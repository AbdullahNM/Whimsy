#!/usr/bin/env python3
"""
tests/test_e2e_integration.py
==============================
Deterministic mock-based end-to-end integration test suite for Whimsy CYOA Engine.

Guarantees:
- 100% deterministic execution
- Zero live LLM calls, zero network access (pure mock / authored fallback)
- Strict validation of turn lifecycle, atomic state commits, telemetry logging,
  semantic drift detection/reconciliation, rollback mechanics, and multi-turn batch archival.
"""

import os
import sys
import copy
import json
import glob
import shutil
import tempfile
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.deterministic_core import Core, Outcome
from ENGINE.transaction_manager import (
    TransactionManager,
    TransactionRollbackError,
    TransactionValidationError,
    check_state_drift,
    reconcile_state,
)
from ENGINE.telemetry import (
    record_turn_telemetry,
    validate_telemetry_record,
    read_campaign_telemetry,
    get_campaign_telemetry_summary,
)
from ENGINE.turn_archiver import (
    get_turn_number,
    MAX_ACTIVE_TURNS,
    ACTIVE_BASELINE_TURNS,
)


class TestE2EIntegration(unittest.TestCase):
    """
    End-to-end integration test suite simulating full narrative turn lifecycles,
    state transactions, and system observability.
    """

    def setUp(self):
        """
        Sets up an isolated test campaign inside tempfile.mkdtemp() with:
        - GAMEPLAY/status.json
        - GAMEPLAY/status.md
        - TURNS/ACTIVE/turn_0001.md
        - Initial state containing energy, stress, purse, clocks, and choices.
        """
        self.test_dir = tempfile.mkdtemp()
        self.campaign_id = "test_campaign"
        self.campaign_dir = os.path.join(self.test_dir, "CAMPAIGNS", self.campaign_id)
        self.gameplay_dir = os.path.join(self.campaign_dir, "GAMEPLAY")
        self.turns_active_dir = os.path.join(self.campaign_dir, "TURNS", "ACTIVE")
        self.turns_archive_dir = os.path.join(self.campaign_dir, "TURNS", "ARCHIVE")

        os.makedirs(self.gameplay_dir, exist_ok=True)
        os.makedirs(self.turns_active_dir, exist_ok=True)
        os.makedirs(self.turns_archive_dir, exist_ok=True)

        self.initial_status = {
            "schema_version": 2,
            "campaign_id": self.campaign_id,
            "turn": 1,
            "character": {
                "name": "Alex Ryder"
            },
            "timeline": "Act I — Dawn of Infiltration",
            "progression": {
                "checkpoint_tokens": 5,
                "checkpoint_max": 5,
                "energy": 100,
                "energy_max": 100,
                "stress": 10,
                "stress_max": 100,
                "xp": 315,
                "xp_threshold": 500
            },
            "purse": {
                "credits": 500,
                "display": "500 ₡"
            },
            "scene_anchor": {
                "location": "Lower Annex Junction Alpha",
                "context": "Staging reconnaissance",
                "time": "08:00 Local"
            },
            "public_state": {
                "flags": {},
                "conditions": [],
                "open_threads": ["Infiltrate the data vault before the lockdown."]
            },
            "clocks": [
                {
                    "id": "contract_deadline",
                    "label": "Contract Deadline",
                    "current": 0,
                    "max": 2,
                    "visibility": "known"
                }
            ],
            "pacing_state": {
                "elapsed_time_minutes": 0,
                "timeline_stamp": "Day 1, 08:00",
                "zoom_level": "detailed_scene",
                "narrative_intensity": 1
            },
            "offered_choices": [
                {
                    "index": 1,
                    "text": "Press forward along primary path."
                },
                {
                    "index": 2,
                    "text": "Inspect your immediate environment for hidden clues or resources."
                },
                {
                    "index": 3,
                    "text": "Confer with your companions to consolidate strategy."
                },
                {
                    "index": 4,
                    "text": "Rest and recover your somatic vitals before proceeding."
                }
            ]
        }

        # Write GAMEPLAY/status.json
        with open(os.path.join(self.gameplay_dir, "status.json"), "w", encoding="utf-8") as f:
            json.dump(self.initial_status, f, indent=2)

        # Write GAMEPLAY/status.md
        self.initial_status_md = (
            "# CURRENT PUBLIC STATE\n\n"
            "## Scene\n\n"
            "- **Turn:** 1\n"
            "- **Protagonist:** Alex Ryder\n"
            "- **Location:** Lower Annex Junction Alpha\n"
            "- **Purse:** 500 ₡\n\n"
            "## Vitals & Progression\n\n"
            "- **Energy:** 100 / 100\n"
            "- **Stress:** 10 / 100\n"
            "- **XP:** 315 / 500\n"
        )
        with open(os.path.join(self.gameplay_dir, "status.md"), "w", encoding="utf-8") as f:
            f.write(self.initial_status_md)

        # Write TURNS/ACTIVE/turn_0001.md
        self.turn_1_content = (
            "# Turn 1\n\n"
            "## Player Action\n"
            "Initial briefing and arrival at staging post.\n\n"
            "## GM Response\n"
            "The subterranean corridor stretches into darkness before you. The security lights pulse softly.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Press forward along primary path.\n"
            "2. Inspect your immediate environment for hidden clues or resources.\n"
            "3. Confer with your companions to consolidate strategy.\n"
            "4. Rest and recover your somatic vitals before proceeding.\n\n"
            "[SYS: Turn 1 | Energy: 100/100 | Checkpoints: 5/5]\n"
        )
        with open(os.path.join(self.turns_active_dir, "turn_0001.md"), "w", encoding="utf-8") as f:
            f.write(self.turn_1_content)

    def tearDown(self):
        """Cleans up the temporary test directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_complete_turn_lifecycle_e2e(self):
        """
        Executes a complete, end-to-end narrative turn lifecycle across 7 steps:
        1. Player Choice
        2. Deterministic Core Resolution
        3. Tiered Narration formatting with valid delimiters
        4. Two-phase State Commit & Archival
        5. Telemetry Recording & Validation
        6. Semantic Drift Injection & Detection
        7. Semantic State Reconciliation
        """
        # --- Step 1 (Player Choice): Action 1 ("Press forward along primary path") ---
        action = 1
        action_text = "Press forward along primary path."

        # --- Step 2 (Deterministic Core Resolution) ---
        outcome: Outcome = Core.resolve(self.initial_status, action, config={"seed": 42})
        self.assertIsInstance(outcome, Outcome)
        self.assertEqual(outcome.next_state["turn"], 2)

        # Assert state deltas: energy decreased, time advanced, clock advanced
        self.assertLess(
            outcome.next_state["progression"]["energy"],
            self.initial_status["progression"]["energy"],
            "Energy did not decrease upon resolving Action 1."
        )
        self.assertEqual(outcome.progression_delta.get("energy"), -5)

        self.assertGreater(
            outcome.next_state["pacing_state"]["elapsed_time_minutes"],
            self.initial_status["pacing_state"]["elapsed_time_minutes"],
            "Elapsed time did not advance upon resolving Action 1."
        )

        initial_clock = self.initial_status["clocks"][0]["current"]
        next_clock = outcome.next_state["clocks"][0]["current"]
        self.assertGreater(next_clock, initial_clock, "Clock did not advance upon resolving Action 1.")
        self.assertEqual(len(outcome.clocks_advanced), 1)
        self.assertEqual(outcome.clocks_advanced[0]["id"], "contract_deadline")

        # --- Step 3 (Tiered Narration: Format narrative prose with valid delimiters) ---
        narrative_prose = (
            "You press forward along the primary path, keeping low and alert as the facility hums around you.\n\n"
            "[XP RESOLUTION: Previous: 315 | Delta: +25 (Path Advance) | New Total: 340 / 500]\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Press forward along primary path.\n"
            "2. Inspect your immediate environment for hidden clues or resources.\n"
            "3. Confer with your companions to consolidate strategy.\n"
            "4. Rest and recover your somatic vitals before proceeding.\n\n"
            "[SYS: Turn 2 | Energy: 95/100 | Checkpoints: 5/5]"
        )

        self.assertIn("[XP RESOLUTION:", narrative_prose)
        self.assertIn("[SYS: Turn 2", narrative_prose)
        self.assertIn("### [OPTIONS & TYPABLE REFERENCE]", narrative_prose)

        # --- Step 4 (2-Phase State Commit & Archival) ---
        tm = TransactionManager(self.campaign_dir)
        tm.stage("status.json", outcome.next_state)
        tm.stage(
            "status.md",
            "# CURRENT PUBLIC STATE\n\n"
            "## Scene\n\n"
            "- **Turn:** 2\n"
            "- **Protagonist:** Alex Ryder\n"
            "- **Location:** Lower Annex Junction Alpha\n"
            "- **Purse:** 500 ₡\n\n"
            "## Vitals & Progression\n\n"
            "- **Energy:** 95 / 100\n"
            "- **Stress:** 10 / 100\n"
            "- **XP:** 340 / 500\n"
        )
        metadata = {
            "turn": 2,
            "action": action_text,
            "progression_delta": outcome.progression_delta,
            "clocks_advanced": outcome.clocks_advanced
        }
        tm.stage_turn(
            turn_number=2,
            player_input=action_text,
            gm_output=narrative_prose,
            metadata=metadata
        )

        commit_result = tm.commit()
        self.assertTrue(commit_result["success"])
        self.assertEqual(commit_result["status"], "committed")

        # Assert temporary files removed
        tmp_files = glob.glob(os.path.join(self.campaign_dir, "**", "*.tmp*"), recursive=True)
        self.assertEqual(len(tmp_files), 0, f"Found lingering .tmp files after commit: {tmp_files}")

        # Assert turn_0002.md created
        turn_2_file = os.path.join(self.turns_active_dir, "turn_0002.md")
        self.assertTrue(os.path.exists(turn_2_file), "turn_0002.md was not created.")
        with open(turn_2_file, "r", encoding="utf-8") as f:
            turn_2_content = f.read()
        self.assertIn(action_text, turn_2_content)
        self.assertIn("[SYS: Turn 2", turn_2_content)

        # Assert status.json contains turn 2
        with open(os.path.join(self.gameplay_dir, "status.json"), "r", encoding="utf-8") as f:
            committed_status = json.load(f)
        self.assertEqual(committed_status["turn"], 2)
        self.assertEqual(committed_status["progression"]["energy"], 95)

        # --- Step 5 (Telemetry Recording) ---
        record = record_turn_telemetry(
            root_dir=self.test_dir,
            campaign_id=self.campaign_id,
            turn=1,
            latency_ms=32.4,
            model="mock-authored-narrator",
            operational_mode="classic_cyoa",
            zoom_level="detailed_scene",
            narrative_intensity=2,
            prompt_tokens=120,
            completion_tokens=65,
            retrieval_hits=1,
            style_violations=[],
            outcome_state_delta=outcome.progression_delta
        )

        telemetry_errors = validate_telemetry_record(record)
        self.assertEqual(len(telemetry_errors), 0, f"Telemetry record validation failed: {telemetry_errors}")

        telemetry_records = read_campaign_telemetry(self.test_dir, self.campaign_id)
        self.assertEqual(len(telemetry_records), 1)

        summary = get_campaign_telemetry_summary(self.test_dir, self.campaign_id)
        self.assertEqual(summary.get("total_turns"), 1)

        # --- Step 6 (Semantic Drift Injection & Detection) ---
        corrupted_status_md = (
            "# CURRENT PUBLIC STATE\n\n"
            "## Scene\n\n"
            "- **Turn:** 99\n"
            "- **Protagonist:** Alex Ryder\n"
            "- **Location:** Lower Annex Junction Alpha\n"
            "- **Purse:** 500 ₡\n"
        )
        with open(os.path.join(self.gameplay_dir, "status.md"), "w", encoding="utf-8") as f:
            f.write(corrupted_status_md)

        has_drift, drift_reasons = check_state_drift(self.campaign_dir)
        self.assertTrue(has_drift, "Semantic state drift was not detected after corrupting status.md.")
        self.assertTrue(
            any("Turn mismatch" in r for r in drift_reasons),
            f"Expected turn mismatch drift reason, got: {drift_reasons}"
        )

        # --- Step 7 (Semantic State Reconciliation) ---
        recon_result = reconcile_state(self.campaign_dir, authoritative_source="json")
        self.assertTrue(recon_result["success"])
        self.assertFalse(recon_result["has_drift"])

        post_drift, post_reasons = check_state_drift(self.campaign_dir)
        self.assertFalse(post_drift, f"State still has drift after reconciliation: {post_reasons}")
        self.assertEqual(len(post_reasons), 0)

        with open(os.path.join(self.gameplay_dir, "status.md"), "r", encoding="utf-8") as f:
            reconciled_md = f.read()
        self.assertIn("- **Turn:** 2", reconciled_md)
        self.assertNotIn("- **Turn:** 99", reconciled_md)

    def test_transaction_rollback_on_failure_e2e(self):
        """
        Simulates failures during transaction processing (invalid JSON and mid-transaction crash)
        and verifies that TransactionManager cleanly rolls back without corrupting existing status.json.
        """
        status_path = os.path.join(self.gameplay_dir, "status.json")
        with open(status_path, "r", encoding="utf-8") as f:
            status_before = json.load(f)

        turn_2_path = os.path.join(self.turns_active_dir, "turn_0002.md")
        self.assertFalse(os.path.exists(turn_2_path))

        # 1. Failure via invalid JSON / schema validation error
        tm_invalid = TransactionManager(self.campaign_dir)
        tm_invalid.stage("status.json", {"corrupted": "state", "no_required_keys": True})
        with self.assertRaises(TransactionValidationError):
            tm_invalid.commit()

        # Verify status.json is untouched
        with open(status_path, "r", encoding="utf-8") as f:
            status_after_invalid = json.load(f)
        self.assertEqual(status_before, status_after_invalid)

        # 2. Failure mid-transaction simulated exception during commit phase
        tm_crash = TransactionManager(self.campaign_dir)
        mutated_status = copy.deepcopy(status_before)
        mutated_status["turn"] = 2
        mutated_status["progression"]["energy"] = 15

        tm_crash.stage("status.json", mutated_status)
        tm_crash.stage_turn(
            turn_number=2,
            player_input="Simulate abort",
            gm_output="Should not persist."
        )

        with self.assertRaises(TransactionRollbackError):
            tm_crash.commit(simulate_failure_at="during_commit")

        # Verify clean rollback: existing status.json is completely preserved
        with open(status_path, "r", encoding="utf-8") as f:
            status_after_crash = json.load(f)
        self.assertEqual(status_before, status_after_crash)

        # Verify turn_0002.md was not written
        self.assertFalse(os.path.exists(turn_2_path))

        # Verify zero lingering temporary files
        tmp_files = glob.glob(os.path.join(self.campaign_dir, "**", "*.tmp*"), recursive=True)
        self.assertEqual(len(tmp_files), 0, f"Lingering tmp files found after rollback: {tmp_files}")

    def test_cross_turn_progression_multi_step_e2e(self):
        """
        Executes Turn 1 -> Turn 2 -> Turn 3 sequentially, asserting energy decrement,
        clock ticking to threshold, and active turn window archiving after batch threshold.
        """
        current_state = dict(self.initial_status)

        # --- Turn 1 -> Turn 2 ---
        outcome_turn_2: Outcome = Core.resolve(current_state, 1, config={"seed": 42})
        self.assertEqual(outcome_turn_2.next_state["turn"], 2)
        self.assertEqual(outcome_turn_2.next_state["progression"]["energy"], 95)
        self.assertEqual(outcome_turn_2.next_state["clocks"][0]["current"], 1)

        tm2 = TransactionManager(self.campaign_dir)
        tm2.stage("status.json", outcome_turn_2.next_state)
        tm2.stage_turn(
            turn_number=2,
            player_input="Press forward along primary path.",
            gm_output="Proceeding into sector two. [SYS: Turn 2 | Checkpoints: 5/5]"
        )
        res2 = tm2.commit()
        self.assertTrue(res2["success"])
        self.assertTrue(os.path.exists(os.path.join(self.turns_active_dir, "turn_0002.md")))

        current_state = outcome_turn_2.next_state

        # --- Turn 2 -> Turn 3 ---
        outcome_turn_3: Outcome = Core.resolve(current_state, 1, config={"seed": 42})
        self.assertEqual(outcome_turn_3.next_state["turn"], 3)
        self.assertEqual(outcome_turn_3.next_state["progression"]["energy"], 90)
        self.assertEqual(outcome_turn_3.next_state["clocks"][0]["current"], 2)

        # Assert clock ticking to threshold (max was configured as 2 in setUp)
        clock_obj = outcome_turn_3.next_state["clocks"][0]
        self.assertGreaterEqual(
            clock_obj["current"],
            clock_obj["max"],
            f"Clock {clock_obj['id']} did not reach threshold (current: {clock_obj['current']}, max: {clock_obj['max']})"
        )
        self.assertTrue(
            any(c["fired"] for c in outcome_turn_3.clocks_advanced if c["id"] == "contract_deadline"),
            "Clock deadline fired event was not triggered when reaching threshold."
        )

        tm3 = TransactionManager(self.campaign_dir)
        tm3.stage("status.json", outcome_turn_3.next_state)
        tm3.stage_turn(
            turn_number=3,
            player_input="Press forward along primary path.",
            gm_output="Threshold reached. Contract deadline elapsed. [SYS: Turn 3 | Checkpoints: 5/5]"
        )
        res3 = tm3.commit()
        self.assertTrue(res3["success"])
        self.assertTrue(os.path.exists(os.path.join(self.turns_active_dir, "turn_0003.md")))

        current_state = outcome_turn_3.next_state

        # --- Active Turn Window Archiving After Batch Threshold ---
        # Prior to reaching MAX_ACTIVE_TURNS (20), turns remain exclusively in TURNS/ACTIVE/
        active_before = glob.glob(os.path.join(self.turns_active_dir, "turn_*.md"))
        archive_before = glob.glob(os.path.join(self.turns_archive_dir, "turn_*.md"))
        self.assertEqual(len(active_before), 3)
        self.assertEqual(len(archive_before), 0)

        # Progress through Turn 4 up to Turn 20 using TransactionManager
        for t in range(4, MAX_ACTIVE_TURNS + 1):
            outcome_t: Outcome = Core.resolve(current_state, 1, config={"seed": 42})
            current_state = outcome_t.next_state

            tm_step = TransactionManager(self.campaign_dir)
            tm_step.stage("status.json", current_state)
            tm_step.stage_turn(
                turn_number=t,
                player_input=f"Progress step {t}",
                gm_output=f"Resolved narrative turn {t}. [SYS: Turn {t} | Checkpoints: 5/5]"
            )
            tm_step.commit()

        # At Turn 20, active turns reached MAX_ACTIVE_TURNS (20), triggering batch archival
        active_after = sorted(
            glob.glob(os.path.join(self.turns_active_dir, "turn_*.md")),
            key=get_turn_number
        )
        archive_after = sorted(
            glob.glob(os.path.join(self.turns_archive_dir, "turn_*.md")),
            key=get_turn_number
        )

        # Batch archival prunes active turns down to ACTIVE_BASELINE_TURNS (15)
        self.assertEqual(
            len(active_after),
            ACTIVE_BASELINE_TURNS,
            f"Expected {ACTIVE_BASELINE_TURNS} active turns, got {len(active_after)}"
        )
        # Oldest batch of 5 turns (Turns 1-5) moved to archive
        self.assertEqual(
            len(archive_after),
            MAX_ACTIVE_TURNS - ACTIVE_BASELINE_TURNS,
            f"Expected {MAX_ACTIVE_TURNS - ACTIVE_BASELINE_TURNS} archived turns, got {len(archive_after)}"
        )

        self.assertEqual(get_turn_number(archive_after[0]), 1)
        self.assertEqual(get_turn_number(archive_after[-1]), 5)
        self.assertEqual(get_turn_number(active_after[0]), 6)
        self.assertEqual(get_turn_number(active_after[-1]), 20)


if __name__ == "__main__":
    unittest.main()
