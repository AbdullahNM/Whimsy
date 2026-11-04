#!/usr/bin/env python3
"""
Unit tests for Persistent Adaptive Narrative Focus Controller (Pacing & Clocks).
Tests:
- Seamless transitions between zoom levels (detailed_scene, short_summary, montage, time_skip)
- Blocking unauthorized time jumps or location changes when unresolved player intentions exist
- Routine tasks (routine training, travel) defaulting to summary/montage unless player requests detailed focus
- Ordinary scenes maintaining low narrative intensity (1-2) without artificial dramatic escalation
- In-game time advancement correctly firing scheduled world events crossed
- Schema compliance with turn_state.schema.json
"""

import os
import sys
import json
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.pacing_controller import (
    PacingController,
    ZOOM_DETAILED_SCENE,
    ZOOM_SHORT_SUMMARY,
    ZOOM_MONTAGE,
    ZOOM_TIME_SKIP,
    VALID_ZOOM_LEVELS,
    SCENE_ROUTINE,
    SCENE_DOWNTIME,
    SCENE_TRAVEL,
    SCENE_CONFLICT,
    SCENE_CONVERSATION,
    SCENE_EXPLORATION,
)
from tests.test_schemas import SimpleSchemaValidator


class TestPacingController(unittest.TestCase):
    def setUp(self):
        self.controller = PacingController()
        schema_path = os.path.join(ROOT_DIR, "GLOBAL", "SCHEMAS", "turn_state.schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            turn_state_schema = json.load(f)
        self.pacing_state_schema = turn_state_schema["properties"]["pacing_state"]

    # --------------------------------------------------------------------------
    # 1. Zoom Level Transitions
    # --------------------------------------------------------------------------

    def test_seamless_transitions_between_zoom_levels(self):
        """Test valid seamless transitions between all 4 zoom levels."""
        pacing = self.controller.create_default_pacing(
            zoom_level=ZOOM_DETAILED_SCENE,
            narrative_intensity=2,
            current_location="Courtyard",
            unresolved_intentions=[],
        )

        # Transition detailed_scene -> short_summary
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="Take a short stroll to the gatehouse.",
            proposed_zoom=ZOOM_SHORT_SUMMARY,
            proposed_time_skip_minutes=15,
        )
        self.assertTrue(allowed, f"detailed_scene -> short_summary failed: {reason}")

        # Transition short_summary -> montage
        pacing["zoom_level"] = ZOOM_SHORT_SUMMARY
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="Spend the next week undergoing conditioning exercises.",
            proposed_zoom=ZOOM_MONTAGE,
            proposed_time_skip_minutes=1440 * 7,
        )
        self.assertTrue(allowed, f"short_summary -> montage failed: {reason}")

        # Transition montage -> time_skip (when no unresolved intentions)
        pacing["zoom_level"] = ZOOM_MONTAGE
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="Fast forward to the day of the evaluation.",
            proposed_zoom=ZOOM_TIME_SKIP,
            proposed_time_skip_minutes=1440,
        )
        self.assertTrue(allowed, f"montage -> time_skip failed: {reason}")

        # Transition time_skip -> detailed_scene
        pacing["zoom_level"] = ZOOM_TIME_SKIP
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="Step onto the testing grounds and address the examiner.",
            proposed_zoom=ZOOM_DETAILED_SCENE,
            proposed_time_skip_minutes=0,
        )
        self.assertTrue(allowed, f"time_skip -> detailed_scene failed: {reason}")

    def test_invalid_zoom_level_rejected(self):
        """Test rejection of non-existent zoom levels."""
        pacing = self.controller.create_default_pacing()
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_zoom="instant_warp_view",
        )
        self.assertFalse(allowed)
        self.assertIn("Invalid zoom level", reason)

    def test_negative_time_skip_rejected(self):
        """Test rejection of negative time skips."""
        pacing = self.controller.create_default_pacing()
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_time_skip_minutes=-60,
        )
        self.assertFalse(allowed)
        self.assertIn("cannot be negative", reason)

    # --------------------------------------------------------------------------
    # 2. Gate: Unresolved Intentions & Unearned Location Jumps
    # --------------------------------------------------------------------------

    def test_blocking_unauthorized_time_jumps_with_unresolved_intentions(self):
        """Test that active unresolved player intentions strictly block time skips."""
        pacing = self.controller.create_default_pacing(
            unresolved_intentions=["Disarm the ticking incendiary device before it detonates"],
            zoom_level=ZOOM_DETAILED_SCENE,
            narrative_intensity=4,
            current_location="Engineering Bay",
        )

        # Attempt time skip via proposed_zoom
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="Go to sleep and wait until tomorrow morning.",
            proposed_zoom=ZOOM_TIME_SKIP,
            proposed_time_skip_minutes=480,
        )
        self.assertFalse(allowed)
        self.assertIn("unresolved intentions exist", reason)

        # Attempt time skip via proposed_time_skip_minutes
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="Wait a couple of hours.",
            proposed_zoom=ZOOM_SHORT_SUMMARY,
            proposed_time_skip_minutes=120,
        )
        self.assertFalse(allowed)
        self.assertIn("unresolved intentions exist", reason)

    def test_allowing_time_skip_with_explicit_permission_or_causal_justification(self):
        """Test that explicit permission or causal justification permits transition past intentions."""
        pacing = self.controller.create_default_pacing(
            unresolved_intentions=["Investigate the strange noises in the pantry"],
            zoom_level=ZOOM_DETAILED_SCENE,
            current_location="Kitchen",
        )

        # Explicit permission flag
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="Abandon the search and go to sleep.",
            proposed_zoom=ZOOM_TIME_SKIP,
            proposed_time_skip_minutes=480,
            explicit_permission=True,
        )
        self.assertTrue(allowed, f"Expected allowed with explicit_permission: {reason}")

        # Explicit permission in action prose
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="Abandoning intention for now, with permission to skip to next morning.",
            proposed_zoom=ZOOM_TIME_SKIP,
            proposed_time_skip_minutes=480,
        )
        self.assertTrue(allowed, f"Expected allowed with action permission cue: {reason}")

    def test_blocking_unearned_location_jumps(self):
        """Test blocking teleportation or unearned location changes without transit."""
        pacing = self.controller.create_default_pacing(
            current_location="Fortress Dungeon",
            active_conflicts=["Guards are blocking the iron door"],
            unresolved_intentions=["Find the prison key"],
        )

        # Jump from dungeon to the capital city without travel or resolution
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="I am now in the Capital Grand Bazaar.",
            proposed_location="Capital Grand Bazaar",
        )
        self.assertFalse(allowed)
        self.assertIn("location jump", reason.lower())

        # Relocation without transit action even without conflicts
        peaceful_pacing = self.controller.create_default_pacing(
            current_location="Village Inn",
            active_conflicts=[],
            unresolved_intentions=[],
        )
        allowed, reason = self.controller.validate_transition(
            current_pacing=peaceful_pacing,
            proposed_action="Browse the market stalls.",
            proposed_location="Distant Mountain Monastery",
        )
        self.assertFalse(allowed)
        self.assertIn("location jump", reason.lower())

        # Valid transit action should be allowed
        allowed, reason = self.controller.validate_transition(
            current_pacing=peaceful_pacing,
            proposed_action="Travel along the eastern road toward the Distant Mountain Monastery.",
            proposed_location="Distant Mountain Monastery",
            proposed_zoom=ZOOM_SHORT_SUMMARY,
        )
        self.assertTrue(allowed, f"Expected travel transition to be allowed: {reason}")

    # --------------------------------------------------------------------------
    # 3. Focus Evaluation: Routine Tasks vs Detailed Focus
    # --------------------------------------------------------------------------

    def test_routine_tasks_default_to_summary_or_montage(self):
        """Test routine training, travel, chores default to summary/montage."""
        # Short routine training -> short_summary
        zoom = self.controller.evaluate_focus("Practice weapon drills in the yard.")
        self.assertIn(zoom, [ZOOM_SHORT_SUMMARY, ZOOM_MONTAGE])

        # Extended multi-week training -> montage
        zoom = self.controller.evaluate_focus("Spend three weeks of daily routine conditioning.")
        self.assertEqual(zoom, ZOOM_MONTAGE)

        # Routine local travel -> short_summary
        zoom = self.controller.evaluate_focus("Walk to the magistrate's office across town.")
        self.assertEqual(zoom, ZOOM_SHORT_SUMMARY)

        # Long multi-week journey -> montage
        zoom = self.controller.evaluate_focus("Embark on the long journey across the desert for two weeks.")
        self.assertEqual(zoom, ZOOM_MONTAGE)

        # Downtime / rest -> short_summary
        zoom = self.controller.evaluate_focus("Eat dinner with the squad and rest for the night.")
        self.assertEqual(zoom, ZOOM_SHORT_SUMMARY)

    def test_routine_tasks_zoom_in_when_player_requests_detail(self):
        """Test that explicit player request ('zoom in', 'elaborate') forces detailed scene."""
        # Player asks to zoom in on training
        zoom = self.controller.evaluate_focus("Zoom in on my practice sparring session with Kaelen.")
        self.assertEqual(zoom, ZOOM_DETAILED_SCENE)

        # Player asks for detailed scene on travel
        zoom = self.controller.evaluate_focus("Elaborate in detail on the walk through the old alleyways.")
        self.assertEqual(zoom, ZOOM_DETAILED_SCENE)

        # Player asks to focus step by step
        zoom = self.controller.evaluate_focus("Focus on the crafting process step by step.")
        self.assertEqual(zoom, ZOOM_DETAILED_SCENE)

    def test_interactive_scenes_evaluate_to_detailed_scene(self):
        """Test dialogue, discoveries, conflicts, and pivotal decisions evaluate to detailed_scene."""
        # Conversation
        zoom = self.controller.evaluate_focus("Ask the quartermaster about the missing shipments.")
        self.assertEqual(zoom, ZOOM_DETAILED_SCENE)

        # Discovery / investigation
        zoom = self.controller.evaluate_focus("Inspect the ciphered ledger for hidden ink markings.")
        self.assertEqual(zoom, ZOOM_DETAILED_SCENE)

        # Combat / conflict
        zoom = self.controller.evaluate_focus("Parry the bandit's dagger and strike back with my pommel.")
        self.assertEqual(zoom, ZOOM_DETAILED_SCENE)

        # Pivotal decision
        zoom = self.controller.evaluate_focus("Decide whether to sign the pact with the guild envoy.")
        self.assertEqual(zoom, ZOOM_DETAILED_SCENE)

    def test_explicit_player_zoom_directives(self):
        """Test explicit player directives for time skip, montage, summary."""
        # Time skip request
        zoom = self.controller.evaluate_focus("Skip to next morning.")
        self.assertEqual(zoom, ZOOM_TIME_SKIP)

        # Fast forward request
        zoom = self.controller.evaluate_focus("Fast forward to the arrival at the gates.")
        self.assertEqual(zoom, ZOOM_TIME_SKIP)

        # Montage request
        zoom = self.controller.evaluate_focus("Give me a training montage over the next few weeks.")
        self.assertEqual(zoom, ZOOM_MONTAGE)

        # Summary request
        zoom = self.controller.evaluate_focus("Briefly summarize the uneventful night shift.")
        self.assertEqual(zoom, ZOOM_SHORT_SUMMARY)

    # --------------------------------------------------------------------------
    # 4. Narrative Intensity & Dramatic Escalation Gate
    # --------------------------------------------------------------------------

    def test_ordinary_scenes_maintain_low_narrative_intensity(self):
        """Test ordinary scenes maintain low narrative intensity (1-2) without artificial escalation."""
        pacing = self.controller.create_default_pacing(
            scene_type=SCENE_ROUTINE,
            narrative_intensity=1,
        )

        intensity = self.controller.recommend_intensity("Eat lunch in the mess hall and talk with friends.", pacing)
        self.assertIn(intensity, [1, 2])

        intensity = self.controller.recommend_intensity("Practice drawing water from the courtyard well.", pacing)
        self.assertIn(intensity, [1, 2])

        intensity = self.controller.recommend_intensity("Travel quietly to the archive.", pacing)
        self.assertIn(intensity, [1, 2])

    def test_dramatic_escalation_gate_blocks_excessive_intensity_jump(self):
        """Test blocking intensity jump > 2 steps without causal justification."""
        pacing = self.controller.create_default_pacing(
            narrative_intensity=1,
            scene_type=SCENE_DOWNTIME,
        )

        # Jump from 1 to 4 (delta 3 > 2) without justification -> Blocked
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="The situation suddenly turns perilous.",
            proposed_intensity=4,
            causal_justification=False,
        )
        self.assertFalse(allowed)
        self.assertIn("Dramatic escalation rejected", reason)
        self.assertIn("exceeds threshold of 2", reason)

        # Jump from 2 to 5 (delta 3 > 2) without justification -> Blocked
        pacing["narrative_intensity"] = 2
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="Everyone is now fighting for their lives.",
            proposed_intensity=5,
            causal_justification=False,
        )
        self.assertFalse(allowed)
        self.assertIn("Dramatic escalation rejected", reason)

        # Jump <= 2 steps (e.g. 1 to 3, or 2 to 4) -> Allowed
        pacing["narrative_intensity"] = 1
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="A tense confrontation begins.",
            proposed_intensity=3,
        )
        self.assertTrue(allowed, f"Expected 2-step jump to be allowed: {reason}")

        # Jump > 2 steps WITH causal justification (e.g. ambush, explosion) -> Allowed
        allowed, reason = self.controller.validate_transition(
            current_pacing=pacing,
            proposed_action="An sudden explosion tears through the wall in an ambush!",
            proposed_intensity=5,
            causal_justification=True,
        )
        self.assertTrue(allowed, f"Expected justified dramatic escalation: {reason}")

    # --------------------------------------------------------------------------
    # 5. In-Game Time Advancement & Event Clocks
    # --------------------------------------------------------------------------

    def test_advance_time_arithmetic_and_timestamps(self):
        """Test deterministic minute arithmetic and timeline stamp advancing."""
        pacing = self.controller.create_default_pacing(
            elapsed_time_minutes=0,
            timeline_stamp="Day 1, 08:00",
        )

        # Advance 120 minutes (2 hours)
        updated, events = self.controller.advance_time(pacing, delta_minutes=120)
        self.assertEqual(updated["elapsed_time_minutes"], 120)
        self.assertEqual(updated["timeline_stamp"], "Day 1, 10:00")
        self.assertEqual(events, [])

        # Advance another 1440 minutes (24 hours -> Day 2)
        updated2, _ = self.controller.advance_time(updated, delta_minutes=1440)
        self.assertEqual(updated2["elapsed_time_minutes"], 1560)
        self.assertEqual(updated2["timeline_stamp"], "Day 2, 10:00")

    def test_scheduled_world_events_trigger_when_crossed(self):
        """Test that in-game time advancement correctly fires scheduled world events crossed."""
        pacing = self.controller.create_default_pacing(
            elapsed_time_minutes=0,
            timeline_stamp="Day 1, 08:00",
            scheduled_events=[
                {
                    "id": "bell_toll",
                    "trigger_time_minutes": 60,
                    "description": "Mid-morning bell tolls across the city.",
                    "fired": False,
                },
                {
                    "id": "patrol_arrival",
                    "trigger_time_minutes": 180,
                    "description": "City watch patrol arrives at the gatehouse.",
                    "fired": False,
                },
                {
                    "id": "nightfall",
                    "trigger_time_minutes": 600,
                    "description": "Sun dips below the horizon, gates lock.",
                    "fired": False,
                },
            ],
        )

        # 1. Advance 90 minutes: bell_toll (60m) triggers, patrol (180m) does not
        step1, triggered1 = self.controller.advance_time(pacing, delta_minutes=90)
        self.assertEqual(step1["elapsed_time_minutes"], 90)
        self.assertEqual(len(triggered1), 1)
        self.assertEqual(triggered1[0]["id"], "bell_toll")
        self.assertTrue(triggered1[0]["fired"])

        # Verify bell_toll is marked fired in state
        bell_event = next(e for e in step1["scheduled_events"] if e["id"] == "bell_toll")
        self.assertTrue(bell_event["fired"])

        # 2. Advance another 100 minutes (90 -> 190): patrol_arrival (180m) triggers, bell_toll does not fire again
        step2, triggered2 = self.controller.advance_time(step1, delta_minutes=100)
        self.assertEqual(step2["elapsed_time_minutes"], 190)
        self.assertEqual(len(triggered2), 1)
        self.assertEqual(triggered2[0]["id"], "patrol_arrival")

        # 3. Advance 300 minutes (190 -> 490): neither fires yet (nightfall is at 600m)
        step3, triggered3 = self.controller.advance_time(step2, delta_minutes=300)
        self.assertEqual(step3["elapsed_time_minutes"], 490)
        self.assertEqual(len(triggered3), 0)

        # 4. Advance 150 minutes (490 -> 640): nightfall (600m) triggers
        step4, triggered4 = self.controller.advance_time(step3, delta_minutes=150)
        self.assertEqual(step4["elapsed_time_minutes"], 640)
        self.assertEqual(len(triggered4), 1)
        self.assertEqual(triggered4[0]["id"], "nightfall")

        # All events should now be fired
        self.assertTrue(all(e["fired"] for e in step4["scheduled_events"]))

    def test_advance_time_with_external_world_events(self):
        """Test passing external world_events to advance_time."""
        pacing = self.controller.create_default_pacing(elapsed_time_minutes=0)
        external_events = [
            {
                "id": "courier_arrives",
                "trigger_time_minutes": 30,
                "description": "Urgent dispatch courier arrives.",
                "fired": False,
            }
        ]
        updated, triggered = self.controller.advance_time(
            current_pacing=pacing,
            delta_minutes=45,
            world_events=external_events,
        )
        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0]["id"], "courier_arrives")
        self.assertTrue(triggered[0]["fired"])

    # --------------------------------------------------------------------------
    # 6. Schema Compliance of Generated State
    # --------------------------------------------------------------------------

    def test_default_pacing_state_schema_compliance(self):
        """Verify that PacingController.create_default_pacing satisfies turn_state schema."""
        pacing = self.controller.create_default_pacing(
            scene_type=SCENE_EXPLORATION,
            scene_objective="Map out subterranean conduits",
            narrative_intensity=2,
            zoom_level=ZOOM_DETAILED_SCENE,
            elapsed_time_minutes=120,
            timeline_stamp="Day 1, 10:00",
            active_conflicts=["Rival scouts in sector"],
            unresolved_intentions=["Locate maintenance hatch"],
            current_location="Conduit Sub-Level 3",
            pending_decisions=["Turn left to vault or right to shaft"],
            pacing_profile="balanced",
            scheduled_events=[
                {
                    "id": "steam_vent_pulse",
                    "trigger_time_minutes": 150,
                    "description": "Thermal steam pulse through main chamber",
                    "fired": False,
                }
            ],
        )

        errors = SimpleSchemaValidator.validate(pacing, self.pacing_state_schema)
        self.assertEqual(errors, [], f"Schema validation errors for default pacing: {errors}")


if __name__ == "__main__":
    unittest.main()
