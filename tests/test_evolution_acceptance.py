#!/usr/bin/env python3
"""
Full Acceptance Regression Suite for Whimsy Evolution Architecture.
Explicitly verifies all requirements from Section F:
a) Classic mode refuses freeform actions without changing state or creating turn files.
b) Freeform mode accepts compound actions.
c) Campaign can start without a predetermined plot (world-first sandbox).
d) Ordinary scenes remain ordinary (intensity 1-2) when no justified escalation occurs.
e) Narrator maintains simple English across extended sessions (style linter verifies zero drift).
f) Time and location never change without authorized transitions (transition guard blocks jumps).
g) Important mysteries remain unresolved until justified in-world discovery.
h) State remains consistent after long sessions, restarts, and retries (idempotency).
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

from ENGINE.mode_validator import ModeValidator
from ENGINE.pacing_controller import (
    PacingController,
    ZOOM_DETAILED_SCENE,
    ZOOM_SHORT_SUMMARY,
    ZOOM_MONTAGE,
    ZOOM_TIME_SKIP
)
from ENGINE.prompt_assembler import PromptAssembler
from ENGINE.style_contract import StyleContractValidator
from ENGINE.transaction_manager import TransactionManager
from tests.test_engine_server import execute_request


class TestEvolutionAcceptance(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.campaigns_root = os.path.join(self.test_dir, "CAMPAIGNS")
        self.campaign_dir = os.path.join(self.campaigns_root, "acceptance_campaign")
        self.gameplay_dir = os.path.join(self.campaign_dir, "GAMEPLAY")
        self.turns_active_dir = os.path.join(self.campaign_dir, "TURNS", "ACTIVE")
        self.wf_dir = os.path.join(self.campaign_dir, "WORLD_FOUNDATION")

        os.makedirs(self.gameplay_dir, exist_ok=True)
        os.makedirs(self.turns_active_dir, exist_ok=True)
        os.makedirs(self.wf_dir, exist_ok=True)

        # Copy GLOBAL directory into test workspace for PromptAssembler rules
        src_global = os.path.join(ROOT_DIR, "GLOBAL")
        dst_global = os.path.join(self.test_dir, "GLOBAL")
        if os.path.isdir(src_global):
            shutil.copytree(src_global, dst_global)

        # Baseline campaign config
        self.config = {
            "id": "acceptance_campaign",
            "operational_mode": "classic_cyoa",
            "title": "Acceptance Test Universe",
            "metrics": [
                {"id": "turn", "label": "Turn", "type": "counter", "path": "turn"},
                {"id": "energy", "label": "Energy", "type": "progress", "path": "progression.energy", "max_path": "progression.energy_max"},
                {"id": "stress", "label": "Stress", "type": "progress", "path": "progression.stress", "max_path": "progression.stress_max"},
                {"id": "funds", "label": "Funds", "type": "text", "path": "purse.display"}
            ],
            "style_contract": {
                "mode": "natural_everyday_english",
                "max_sentence_words": 35,
                "ban_stem_calculus_jargon": True,
                "ban_decorative_microsfx": True,
                "ban_forced_cliffhangers": True,
                "ban_narrator_praise": True,
                "ban_formulaic_closings": True
            }
        }
        with open(os.path.join(self.campaign_dir, "campaign_config.json"), "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

        # Baseline status.json
        self.status = {
            "schema_version": 2,
            "campaign_id": "acceptance_campaign",
            "turn": 1,
            "timeline": "Act I - Dawn of Chapter One",
            "character": {
                "name": "Alex Mercer",
                "archetype": "Specialist"
            },
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
                "display": "500 credits"
            },
            "public_state": {
                "flags": {},
                "conditions": [],
                "open_threads": ["Decide whether to accept the contract."]
            },
            "clocks": [],
            "scene_anchor": {
                "location": "Sub-Level 4 Staging Room",
                "context": "Reviewing contract offer.",
                "time": "06:00 Local Cycle"
            },
            "pacing_state": {
                "scene_type": "exploration",
                "scene_objective": "Review initial contract terms.",
                "narrative_intensity": 1,
                "zoom_level": "detailed_scene",
                "elapsed_time_minutes": 0,
                "timeline_stamp": "Day 1, 06:00",
                "active_conflicts": [],
                "unresolved_intentions": ["Decide whether to accept the contract."],
                "current_location": "Sub-Level 4 Staging Room",
                "pending_decisions": ["Accept contract"],
                "pacing_profile": "balanced",
                "scheduled_events": [
                    {
                        "id": "deadline_warning",
                        "trigger_time_minutes": 120,
                        "description": "Contract offer window closing.",
                        "fired": False
                    }
                ]
            }
        }
        with open(os.path.join(self.gameplay_dir, "status.json"), "w", encoding="utf-8") as f:
            json.dump(self.status, f, indent=2)

        self.status_md = "# Status\n- **Energy**: 100 / 100\n- **Stress**: 10 / 100\n"
        with open(os.path.join(self.gameplay_dir, "status.md"), "w", encoding="utf-8") as f:
            f.write(self.status_md)

        self.items_md = "# Items\n- **Current Coin**: `500 credits`\n"
        with open(os.path.join(self.gameplay_dir, "items.md"), "w", encoding="utf-8") as f:
            f.write(self.items_md)

        # Baseline turn 1 with offered choices
        turn_1_content = (
            "# Turn 1\n\n"
            "You review the contract on your datapad.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Accept Contract Alpha: Infiltrate via the ventilation ducts.\n"
            "2. Accept Contract Beta: Pose as a courier at the main lobby.\n"
            "3. Delay decision to inspect the terminal logs.\n\n"
            "[SYS: Turn 1 | Energy: 100 / 100 | Stress: 10 / 100 | Funds: 500 credits | Checkpoints: 5/5]\n"
        )
        with open(os.path.join(self.turns_active_dir, "turn_0001.md"), "w", encoding="utf-8") as f:
            f.write(turn_1_content)

        # Baseline world foundation (World-first initialization)
        self.world_foundation = {
            "campaign_id": "acceptance_campaign",
            "schema_version": "1.0.0",
            "world_name": "Autonomous Station Core",
            "overview": "A modular orbital station operating under environmental scarcity and independent faction tensions.",
            "immutable_facts": [
                {
                    "id": "FACT-01",
                    "category": "physics",
                    "statement": "Atmospheric pressure is maintained strictly by geothermal generators on Sub-Level 8."
                },
                {
                    "id": "FACT-02",
                    "category": "geography",
                    "statement": "The station consists of four concentric rings separated by pressure bulkheads."
                }
            ],
            "mutable_world_state": {
                "active_epoch": "Solar Cycle 42 - Reconstruction",
                "factions_control": {
                    "Transit Authority": "High Ring Rail Terminals",
                    "Reclamation Guild": "Scrap Sectors"
                },
                "global_tensions_index": "Moderate - resource rationing in effect"
            },
            "factions_and_tensions": [
                {
                    "id": "transit_authority",
                    "name": "Transit Authority",
                    "agenda": "Control freight and travel lines across the central ring.",
                    "objectives": ["Automate transit locks", "Impound unauthorized couriers"],
                    "tensions": [
                        {
                            "target_entity": "Reclamation Guild",
                            "source_of_friction": "Dispute over scrap conduits",
                            "intensity": "simmering"
                        }
                    ]
                }
            ],
            "npc_knowledge": {
                "handler_cross": {
                    "knows": ["Contract Alpha parameters", "Ventilation blueprint"],
                    "does_not_know": ["Identity of rival operative"],
                    "falsely_believes": ["Main lobby cameras are unmonitored"]
                }
            },
            "rumors_and_beliefs": [
                {
                    "claim": "Sub-Level 8 reactors are leaking heavy coolant.",
                    "believed_by": "Maintenance technicians",
                    "veracity": "unverified"
                }
            ],
            "unresolved_mysteries": [
                {
                    "id": "MYSTERY-01",
                    "title": "The Severance Signal",
                    "secret_truth": "The blackout was deliberately triggered by the Syndicate director.",
                    "discovered": False,
                    "discovery_conditions": "Decode encrypted telemetry from the black box in Sub-Level 8."
                },
                {
                    "id": "MYSTERY-02",
                    "title": "Old Station Archive",
                    "secret_truth": "Decommissioned sector contains auxiliary solar capacitors.",
                    "discovered": True,
                    "discovery_conditions": "Inspected salvage logs."
                }
            ]
        }
        with open(os.path.join(self.wf_dir, "world_foundation.json"), "w", encoding="utf-8") as f:
            json.dump(self.world_foundation, f, indent=2)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # Requirement A: Classic Mode Refuses Freeform Actions Without Mutation
    # -------------------------------------------------------------------------
    def test_acceptance_a_classic_mode_refuses_freeform_actions_without_mutation(self):
        """
        Classic mode refuses freeform actions and compound actions without
        changing state or creating turn files.
        """
        turns_before = sorted(os.listdir(self.turns_active_dir))
        self.assertEqual(turns_before, ["turn_0001.md"])
        with open(os.path.join(self.gameplay_dir, "status.json"), "r", encoding="utf-8") as f:
            status_before = json.load(f)

        # 1. Test freeform action rejection
        payload_freeform = {
            "action": "I attempt to pick the electronic lock and steal the officer's keycard.",
            "campaign": "acceptance_campaign",
            "campaign_dir": self.campaign_dir,
            "root_dir": self.test_dir,
            "operational_mode": "classic_cyoa",
            "currentTurn": 1,
            "commit": True
        }
        status_code, headers, body = execute_request("POST", "/generate", json.dumps(payload_freeform).encode("utf-8"))
        self.assertEqual(status_code, 400)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("error"), "INVALID_ACTION")
        self.assertIn("Arbitrary freeform actions are not permitted", data.get("message", ""))

        # 2. Test compound action rejection in classic mode
        payload_compound = {
            "action": "1 and then inspect the security logs",
            "campaign": "acceptance_campaign",
            "campaign_dir": self.campaign_dir,
            "root_dir": self.test_dir,
            "operational_mode": "classic_cyoa",
            "currentTurn": 1,
            "commit": True
        }
        status_code, headers, body = execute_request("POST", "/generate", json.dumps(payload_compound).encode("utf-8"))
        self.assertEqual(status_code, 400)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("error"), "INVALID_ACTION")
        self.assertIn("Compound actions are not permitted", data.get("message", ""))

        # 3. Direct ModeValidator check
        is_val, err, _ = ModeValidator.validate_action(
            "I want to jump out the window",
            mode="classic_cyoa",
            campaign_id="acceptance_campaign",
            root_dir=self.test_dir
        )
        self.assertFalse(is_val)

        # 4. Strict assertion: State and disk files MUST NOT have mutated
        turns_after = sorted(os.listdir(self.turns_active_dir))
        self.assertEqual(turns_after, ["turn_0001.md"], "No new turn files should be created on rejected actions")

        with open(os.path.join(self.gameplay_dir, "status.json"), "r", encoding="utf-8") as f:
            status_after = json.load(f)
        self.assertEqual(status_before, status_after, "State must remain unmutated on rejected action")

    # -------------------------------------------------------------------------
    # Requirement B: Freeform Mode Accepts Compound Actions
    # -------------------------------------------------------------------------
    def test_acceptance_b_freeform_mode_accepts_compound_actions(self):
        """
        Freeform mode accepts compound actions and arbitrary prose.
        """
        compound_actions = [
            "1 and then search the desk for hidden documents",
            "Infiltrate the server room, disable the camera, and download the ledger",
            "Confer with Handler Cross, then prepare the grappling equipment"
        ]

        for action in compound_actions:
            # 1. ModeValidator directly
            is_valid, err, parsed = ModeValidator.validate_action(
                action=action,
                mode="freeform_simulation",
                campaign_id="acceptance_campaign",
                root_dir=self.test_dir
            )
            self.assertTrue(is_valid, f"Expected action to be accepted in freeform mode: {action}")
            self.assertEqual(parsed.get("mode"), "freeform_simulation")
            self.assertEqual(parsed.get("text"), action)

            # 2. Engine endpoint execution
            payload = {
                "action": action,
                "campaign": "acceptance_campaign",
                "campaign_dir": self.campaign_dir,
                "root_dir": self.test_dir,
                "operational_mode": "freeform_simulation",
                "currentTurn": 1,
                "commit": False
            }
            status_code, headers, body = execute_request("POST", "/generate", json.dumps(payload).encode("utf-8"))
            self.assertEqual(status_code, 200)
            data = json.loads(body.decode("utf-8"))
            self.assertIn("response", data)
            self.assertEqual(data.get("mode"), "freeform_simulation")

    # -------------------------------------------------------------------------
    # Requirement C: World-First Sandbox Initialization Without Predetermined Plot
    # -------------------------------------------------------------------------
    def test_acceptance_c_world_first_sandbox_without_predetermined_plot(self):
        """
        Campaign starts without a predetermined plot (world-first sandbox).
        Loads immutable facts, autonomous factions, and epistemic boundaries.
        """
        assembler = PromptAssembler(self.test_dir)
        prompt = assembler.build_system_prompt("acceptance_campaign")

        # Verify world foundation components in system prompt
        self.assertIn("WORLD FOUNDATION & EPISTEMIC SEPARATION", prompt)
        self.assertIn("FACT-01", prompt)
        self.assertIn("Atmospheric pressure is maintained strictly by geothermal generators", prompt)
        self.assertIn("Transit Authority", prompt)
        self.assertIn("Dispute over scrap conduits", prompt)
        self.assertIn("handler_cross", prompt)
        self.assertIn("Verified Known Truths: Contract Alpha parameters", prompt)
        self.assertIn("Sub-Level 8 reactors are leaking heavy coolant", prompt)

        # Verify absence of railroad plot scripts
        self.assertNotIn("Chapter 1: The Hero Meets the Mentor at the Tavern", prompt)

    # -------------------------------------------------------------------------
    # Requirement D: Ordinary Scenes Remain Ordinary (Intensity 1-2)
    # -------------------------------------------------------------------------
    def test_acceptance_d_ordinary_scenes_remain_ordinary_intensity_1_to_2(self):
        """
        Ordinary scenes remain ordinary (narrative intensity 1-2) when no
        justified escalation occurs.
        """
        pacing_ctrl = PacingController()
        ordinary_actions = [
            "Eat a quiet meal with squad members in the mess hall",
            "Study the station maintenance manual in my quarters",
            "Walk down the quiet corridor toward the logistics office",
            "Rest and recover in the crew bunk before next shift",
            "Confer with Handler Cross regarding standard procedures",
            "Inspect the empty storage containers in the warehouse"
        ]

        for action in ordinary_actions:
            rec_intensity = pacing_ctrl.recommend_intensity(action, self.status["pacing_state"])
            self.assertIn(rec_intensity, [1, 2], f"Action '{action}' escalated inappropriately to {rec_intensity}")

        # Contrast with genuine escalation cues
        combat_intensity = pacing_ctrl.recommend_intensity("Sudden ambush by armed raiders! Roll and fight!", self.status["pacing_state"])
        self.assertGreaterEqual(combat_intensity, 3)

        lethal_intensity = pacing_ctrl.recommend_intensity("Life or death: catastrophic explosion in the reactor core!", self.status["pacing_state"])
        self.assertGreaterEqual(lethal_intensity, 3)

    # -------------------------------------------------------------------------
    # Requirement E: Narrator Maintains Simple English Across Extended Sessions
    # -------------------------------------------------------------------------
    def test_acceptance_e_style_linter_zero_drift_extended_session(self):
        """
        Narrator maintains simple everyday English across extended sessions.
        Style contract linter verifies zero drift.
        """
        validator = StyleContractValidator(self.config["style_contract"])

        # Extended multi-turn session simulation (clean natural English turns)
        sample_prose_turns = [
            "You step through the airlock door into the docking bay. The morning shift is already underway as cargo cranes swing overhead.",
            "The handler hands you a small glass vial and nods toward the northern corridor. You tuck it securely into your utility pocket.",
            "A low metallic hum vibrates through the floor plates as the rail carriage slows to a smooth halt at Terminal Bay B.",
            "You examine the maintenance terminal screen. Three green indicator lights confirm that the primary power coupling is intact.",
            "The technician wipes grease from his gloves and looks up from the workbench. He gestures toward the spare battery cells on the rack.",
            "You cross the quiet catwalk overlooking the lower sorting yard. Below, automated loaders move steel shipping containers in silence.",
            "You sit on the edge of the cot and check your field kit. The flashlight, ration bars, and diagnostic tool are in their proper slots.",
            "The merchant checks the serial stamps on your credits before setting the replacement filter on the counter between you.",
            "You lean against the damp bulkhead and wait as the patrol team moves past the far end of the service corridor.",
            "The briefing file finishes loading onto your datapad. The schematic details three accessible routes into the lower scrap sector."
        ]

        for idx, turn_prose in enumerate(sample_prose_turns, start=1):
            is_valid, violations, score = validator.validate_prose(turn_prose)
            self.assertTrue(is_valid, f"Turn {idx} failed style validation: {violations}")
            self.assertEqual(score, 1.0, f"Turn {idx} score drifted below 1.0: {score}")
            self.assertEqual(len(violations), 0)

        # Prohibited patterns must be caught immediately
        bad_turns = [
            ("STEM Jargon", "The reynolds quotient of the atmospheric vent indicates a second-order decay constant."),
            ("Decorative micro-SFX", "You ate your soup as blue sparks danced on your fork and raw power crackled."),
            ("Narrator praise", "With breathtaking prowess and superhuman precision, you demonstrated your prodigious talent."),
            ("Formulaic closing", "The decision is made. What will you do next?")
        ]
        for name, bad_prose in bad_turns:
            is_valid, violations, score = validator.validate_prose(bad_prose)
            self.assertFalse(is_valid, f"Expected '{name}' to fail style check")
            self.assertGreater(len(violations), 0)
            self.assertLess(score, 1.0)

    # -------------------------------------------------------------------------
    # Requirement F: Transition Guard Blocks Unauthorized Time and Location Jumps
    # -------------------------------------------------------------------------
    def test_acceptance_f_transition_guard_blocks_unauthorized_jumps(self):
        """
        Time and location never change without authorized transitions.
        Transition guard blocks jumps when unresolved intentions exist.
        """
        pacing_ctrl = PacingController()
        current_pacing = self.status["pacing_state"]
        # current_pacing has unresolved_intentions: ["Decide whether to accept the contract."]

        # 1. Unapproved time skip blocked
        allowed, reason = pacing_ctrl.validate_transition(
            current_pacing=current_pacing,
            proposed_action="Wait until next morning",
            proposed_zoom=ZOOM_TIME_SKIP,
            proposed_time_skip_minutes=480
        )
        self.assertFalse(allowed)
        self.assertIn("unresolved intentions exist", reason)

        # 2. Unearned location jump blocked
        allowed, reason = pacing_ctrl.validate_transition(
            current_pacing=current_pacing,
            proposed_action="Look around",
            proposed_location="Apex Luxury Spire"
        )
        self.assertFalse(allowed)
        self.assertIn("location jump", reason)

        # 3. Via HTTP /generate endpoint
        payload = {
            "action": "Wait until tomorrow",
            "campaign": "acceptance_campaign",
            "campaign_dir": self.campaign_dir,
            "root_dir": self.test_dir,
            "operational_mode": "freeform_simulation",
            "proposed_zoom": ZOOM_TIME_SKIP,
            "proposed_time_skip_minutes": 480,
            "pacing_state": current_pacing,
            "currentTurn": 1
        }
        status_code, headers, body = execute_request("POST", "/generate", json.dumps(payload).encode("utf-8"))
        self.assertEqual(status_code, 400)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("error"), "TRANSITION_REJECTED")
        self.assertIn("unresolved intentions", data.get("message", ""))

        # 4. Authorized transitions with explicit permission succeed
        allowed_with_perm, reason = pacing_ctrl.validate_transition(
            current_pacing=current_pacing,
            proposed_action="Wait until morning with permission, postponing contract intention",
            proposed_zoom=ZOOM_TIME_SKIP,
            proposed_time_skip_minutes=480,
            explicit_permission=True
        )
        self.assertTrue(allowed_with_perm)

    # -------------------------------------------------------------------------
    # Requirement G: Mysteries Remain Unresolved Until Justified In-World Discovery
    # -------------------------------------------------------------------------
    def test_acceptance_g_mysteries_remain_unresolved_until_justified_discovery(self):
        """
        Important mysteries remain unresolved until justified in-world discovery.
        Hidden secrets are explicitly marked hidden from protagonist view.
        """
        assembler = PromptAssembler(self.test_dir)
        wf_text = assembler.load_world_foundation("acceptance_campaign")

        # MYSTERY-01 has discovered: false
        self.assertIn("[HIDDEN FROM PROTAGONIST VIEW - CANON SECRET] **The Severance Signal**", wf_text)
        self.assertIn("Discovery condition: Decode encrypted telemetry", wf_text)

        # MYSTERY-02 has discovered: true
        self.assertIn("[DISCOVERED] **Old Station Archive**", wf_text)
        self.assertNotIn("[HIDDEN FROM PROTAGONIST VIEW - CANON SECRET] **Old Station Archive**", wf_text)

        # Update world foundation: justified discovery achieved
        wf_path = os.path.join(self.wf_dir, "world_foundation.json")
        with open(wf_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["unresolved_mysteries"][0]["discovered"] = True
        with open(wf_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Reload world foundation: now revealed as discovered
        updated_wf_text = assembler.load_world_foundation("acceptance_campaign")
        self.assertIn("[DISCOVERED] **The Severance Signal**", updated_wf_text)

    # -------------------------------------------------------------------------
    # Requirement H: State Consistency & Idempotency on Retries and Restarts
    # -------------------------------------------------------------------------
    def test_acceptance_h_state_consistency_and_idempotency_on_retries_and_restarts(self):
        """
        State remains consistent after long sessions, restarts, and retries.
        Idempotency prevents duplicate resource/relationship changes.
        """
        tx_mgr = TransactionManager(self.campaign_dir)
        action = "1. Accept Contract Alpha: Infiltrate via the ventilation ducts."
        turn_num = 1
        expected_tx_id = TransactionManager.generate_transaction_id(turn_num, action)

        gm_output = (
            "You slip into the ventilation shaft. The duct is tight and dusty, but your scanner guides you forward.\n\n"
            "### [OPTIONS & TYPABLE REFERENCE]\n"
            "1. Proceed to the server room junction.\n"
            "2. Stop to inspect the wire tap.\n\n"
            "[CURRENCY RESOLUTION: Previous: 500 credits | Delta: -50 credits (equipment fee) | New Purse: 450 credits]\n"
            "[SYS: Turn 2 | Energy: 90 / 100 | Stress: 20 / 100 | Funds: 450 credits | Checkpoints: 5/5]\n"
        )

        # 1. Execute initial turn commit
        result = tx_mgr.execute_narrative_turn(
            campaign_dir=self.campaign_dir,
            turn=turn_num,
            action=action,
            gm_output=gm_output
        )
        self.assertEqual(result.get("status"), "committed")
        self.assertEqual(result.get("transaction_id"), expected_tx_id)

        # Verify state mutated accurately on disk
        with open(os.path.join(self.gameplay_dir, "status.json"), "r", encoding="utf-8") as f:
            status_t1 = json.load(f)
        self.assertEqual(status_t1.get("transaction_id"), expected_tx_id)
        self.assertEqual(status_t1["purse"]["credits"], 450)

        # 2. Retry / Duplicate request (simulate network disconnect, retry button, or replay)
        committed_tx = TransactionManager.get_committed_transaction(
            campaign_dir=self.campaign_dir,
            transaction_id=expected_tx_id,
            turn=turn_num,
            action=action
        )
        self.assertIsNotNone(committed_tx, "Committed transaction must be found in transaction log")
        self.assertEqual(committed_tx.get("transaction_id"), expected_tx_id)

        # 3. Simulate engine /generate request with retry
        payload_retry = {
            "action": action,
            "campaign": "acceptance_campaign",
            "campaign_dir": self.campaign_dir,
            "root_dir": self.test_dir,
            "operational_mode": "classic_cyoa",
            "currentTurn": turn_num,
            "commit": True
        }
        status_code, headers, body = execute_request("POST", "/generate", json.dumps(payload_retry).encode("utf-8"))
        self.assertEqual(status_code, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("transaction_id"), expected_tx_id)

        # Re-check disk: credits MUST still be 450 (NOT deducted again to 400!)
        with open(os.path.join(self.gameplay_dir, "status.json"), "r", encoding="utf-8") as f:
            status_after_retry = json.load(f)
        self.assertEqual(status_after_retry["purse"]["credits"], 450, "Idempotency must prevent duplicate resource deductions")


if __name__ == "__main__":
    unittest.main()
