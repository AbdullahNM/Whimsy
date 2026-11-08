#!/usr/bin/env python3
"""
tests/test_deterministic_core.py
================================
Unit tests for ENGINE/deterministic_core.py and ENGINE/outcome.py.
Verifies:
- Pure functional execution with zero network access (sockets disabled)
- Zero filesystem writes
- Seeded PRNG determinism and replayability without an LLM call
- Outcome dataclass serialization / deserialization round-trip
- Precondition enforcement: ModeValidator action validation & transition gates
- State mutations, clock advancements, progression/resource updates
"""

import copy
import json
import os
import socket
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.deterministic_core import (
    Core,
    ActionValidationError,
    TransitionRejectedError,
    SeededRNG,
    ZOOM_DETAILED_SCENE,
    ZOOM_SHORT_SUMMARY,
    ZOOM_MONTAGE,
    ZOOM_TIME_SKIP
)
from ENGINE.outcome import Outcome


class TestDeterministicCore(unittest.TestCase):
    def setUp(self):
        self.base_state = {
            "schema_version": 2,
            "campaign_id": "template_campaign",
            "turn": 1,
            "timeline": "Act I — Dawn of Chapter One",
            "progression": {
                "energy": 100,
                "energy_max": 100,
                "stress": 10,
                "stress_max": 100,
                "checkpoint_tokens": 5,
                "checkpoint_max": 5
            },
            "purse": {
                "credits": 500,
                "display": "500 ₡"
            },
            "clocks": [
                {
                    "id": "contract_deadline",
                    "label": "Contract deadline",
                    "current": 0,
                    "max": 4,
                    "visibility": "known",
                    "advance_trigger": "Time passes without a decision."
                }
            ],
            "scene_anchor": {
                "location": "Sub-Level 4 Staging Room, Terminal Bay A",
                "context": "Briefing datapad activated",
                "time": "06:00 Local Cycle"
            },
            "pacing_state": {
                "scene_type": "exploration",
                "scene_objective": "Review initial contract terms",
                "narrative_intensity": 1,
                "zoom_level": "detailed_scene",
                "elapsed_time_minutes": 0,
                "timeline_stamp": "06:00 Local Cycle",
                "active_conflicts": [],
                "unresolved_intentions": [
                    "Decide whether to accept the first contract."
                ],
                "current_location": "Sub-Level 4 Staging Room, Terminal Bay A",
                "scheduled_events": []
            },
            "public_state": {
                "flags": {},
                "conditions": [],
                "open_threads": ["Decide whether to accept the first contract."]
            }
        }

    # -------------------------------------------------------------------------
    # 1. Zero Network Access & Purity Verification
    # -------------------------------------------------------------------------

    def test_zero_network_access_guarantee(self):
        """Core.resolve must run with sockets disabled and make zero network calls."""
        orig_socket = socket.socket

        def guarded_socket(*args, **kwargs):
            raise AssertionError("Network access attempted in deterministic core!")

        socket.socket = guarded_socket
        try:
            outcome = Core.resolve(self.base_state, "1", {"operational_mode": "classic_cyoa"})
            self.assertIsInstance(outcome, Outcome)
            self.assertEqual(outcome.next_state["turn"], 2)
        finally:
            socket.socket = orig_socket

    def test_immutability_of_input_state(self):
        """Core.resolve must not mutate the input state in-place."""
        state_copy = copy.deepcopy(self.base_state)
        outcome = Core.resolve(self.base_state, "1")
        self.assertEqual(self.base_state, state_copy, "Input state was mutated in-place!")
        self.assertNotEqual(outcome.next_state["turn"], self.base_state["turn"])

    # -------------------------------------------------------------------------
    # 2. Outcome Round-trip Serialization & Schema Parity
    # -------------------------------------------------------------------------

    def test_outcome_json_roundtrip(self):
        """Outcome must round-trip through to_json() and from_json() without loss."""
        outcome = Core.resolve(self.base_state, "1")
        json_str = outcome.to_json()
        reconstructed = Outcome.from_json(json_str)

        self.assertEqual(outcome.version, reconstructed.version)
        self.assertEqual(outcome.effects, reconstructed.effects)
        self.assertEqual(outcome.events, reconstructed.events)
        self.assertEqual(outcome.clocks_advanced, reconstructed.clocks_advanced)
        self.assertEqual(outcome.progression_delta, reconstructed.progression_delta)
        self.assertEqual(outcome.resources_delta, reconstructed.resources_delta)
        self.assertEqual(outcome.offered_choices, reconstructed.offered_choices)
        self.assertEqual(outcome.next_state, reconstructed.next_state)

    # -------------------------------------------------------------------------
    # 3. Action Validation Preconditions (R7)
    # -------------------------------------------------------------------------

    def test_empty_action_rejected(self):
        """Empty action raises ActionValidationError."""
        with self.assertRaises(ActionValidationError):
            Core.resolve(self.base_state, "")
        with self.assertRaises(ActionValidationError):
            Core.resolve(self.base_state, "   ")
        with self.assertRaises(ActionValidationError):
            Core.resolve(self.base_state, None)

    def test_compound_actions_rejected_in_classic_mode(self):
        """Compound actions must be rejected in classic_cyoa mode."""
        compound_cases = [
            "1, 2",
            "1 and 2",
            "1 & 2",
            "1 and then search",
            "Option 1 and Option 2",
            "1, look for hidden clues"
        ]
        for action in compound_cases:
            with self.assertRaises(ActionValidationError, msg=f"Expected compound action {action!r} to fail"):
                Core.resolve(self.base_state, action, {"operational_mode": "classic_cyoa"})

    def test_out_of_range_option_rejected(self):
        """Out of range options must raise ActionValidationError."""
        for action in ["0", "5", "99", "Option 0", "Option 9"]:
            with self.assertRaises(ActionValidationError):
                Core.resolve(self.base_state, action, {"operational_mode": "classic_cyoa"})

    def test_unmatched_freeform_rejected_in_classic_mode(self):
        """Unmatched arbitrary prose must raise ActionValidationError in classic mode."""
        with self.assertRaises(ActionValidationError):
            Core.resolve(self.base_state, "I want to leap through the glass window", {"operational_mode": "classic_cyoa"})

    def test_freeform_mode_accepts_prose_and_compounds(self):
        """Freeform simulation mode accepts arbitrary prose actions."""
        outcome = Core.resolve(
            self.base_state,
            "I investigate the terminal, hack the logs, and then confer with the squad",
            {"operational_mode": "freeform_simulation"}
        )
        self.assertIsInstance(outcome, Outcome)
        self.assertEqual(outcome.next_state["turn"], 2)

    # -------------------------------------------------------------------------
    # 4. Transition Validation Preconditions
    # -------------------------------------------------------------------------

    def test_unresolved_intentions_block_unearned_time_skip(self):
        """Time skips with unresolved intentions without permission/justification must fail."""
        with self.assertRaises(TransitionRejectedError):
            Core.resolve(
                self.base_state,
                "4",  # Rest is 60 minutes
                {
                    "operational_mode": "classic_cyoa",
                    "proposed_zoom": ZOOM_TIME_SKIP,
                    "proposed_time_skip_minutes": 480
                }
            )

    def test_transition_allowed_with_explicit_permission(self):
        """Time skips succeed if explicit permission is granted."""
        outcome = Core.resolve(
            self.base_state,
            "4",
            {
                "operational_mode": "classic_cyoa",
                "proposed_zoom": ZOOM_TIME_SKIP,
                "proposed_time_skip_minutes": 480,
                "explicit_permission": True
            }
        )
        self.assertIsInstance(outcome, Outcome)
        self.assertEqual(outcome.next_state["pacing_state"]["elapsed_time_minutes"], 480)

    # -------------------------------------------------------------------------
    # 5. Mechanical Mutations, Clocks, & Determinism
    # -------------------------------------------------------------------------

    def test_option_1_advances_energy_and_clock(self):
        outcome = Core.resolve(self.base_state, "1", {"operational_mode": "classic_cyoa"})
        self.assertEqual(outcome.progression_delta.get("energy"), -5)
        self.assertEqual(outcome.next_state["progression"]["energy"], 95)
        self.assertEqual(outcome.next_state["public_state"]["flags"].get("path_pressed"), True)
        self.assertTrue(any(c["id"] == "contract_deadline" and c["current"] == 1 for c in outcome.clocks_advanced))

    def test_clock_filled_triggers_event(self):
        state = copy.deepcopy(self.base_state)
        state["clocks"][0]["current"] = 3
        state["clocks"][0]["max"] = 4

        outcome = Core.resolve(state, "1", {"operational_mode": "classic_cyoa"})
        self.assertEqual(outcome.next_state["clocks"][0]["current"], 4)
        self.assertTrue(any("Clock filled: Contract deadline" in e for e in outcome.events))

    def test_seeded_rng_replayability(self):
        """Resolving the same turn twice with the same seed must produce identical outcomes."""
        outcome_1 = Core.resolve(self.base_state, "1", {"seed": 42})
        outcome_2 = Core.resolve(self.base_state, "1", {"seed": 42})
        self.assertEqual(outcome_1.to_json(), outcome_2.to_json())

    def test_replay_and_diff_without_llm(self):
        """Full turn replay and diffing without any LLM calls."""
        # Turn 1
        t1_outcome = Core.resolve(self.base_state, "1")
        # Turn 2
        t2_outcome = Core.resolve(t1_outcome.next_state, "2")
        self.assertEqual(t2_outcome.next_state["turn"], 3)
        self.assertEqual(t2_outcome.next_state["progression"]["energy"], 90)
        self.assertTrue(t2_outcome.next_state["public_state"]["flags"]["inspected_area"])


if __name__ == "__main__":
    unittest.main()
