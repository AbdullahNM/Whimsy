#!/usr/bin/env python3
"""
Unit and integration tests for ENGINE/transaction_manager.py
Tests:
- Deterministic transaction IDs
- Atomic commit across multiple files (JSON and Markdown)
- Rollback on simulated failures and validation errors preserving exact state
- Idempotency and retry safety preventing duplicate deltas
- Decoupling narration from state mutation
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

from ENGINE.transaction_manager import (
    TransactionManager,
    TransactionError,
    TransactionValidationError,
    TransactionRollbackError
)


class TestTransactionManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.campaign_dir = os.path.join(self.test_dir, "test_campaign")
        self.gameplay_dir = os.path.join(self.campaign_dir, "GAMEPLAY")
        self.turns_active_dir = os.path.join(self.campaign_dir, "TURNS", "ACTIVE")

        os.makedirs(self.gameplay_dir, exist_ok=True)
        os.makedirs(self.turns_active_dir, exist_ok=True)

        # Baseline status.json conforming to turn_state schema
        self.initial_status = {
            "schema_version": 2,
            "campaign_id": "test_campaign",
            "turn": 1,
            "timeline": "Act I — Dawn of Chapter One",
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
                "location": "Staging Room Bay A",
                "context": "Initial briefing",
                "time": "06:00 Local"
            },
            "public_state": {
                "flags": {},
                "conditions": [],
                "open_threads": ["Decide whether to accept the contract."]
            },
            "clocks": [
                {
                    "id": "deadline",
                    "label": "Contract Deadline",
                    "current": 0,
                    "max": 4,
                    "visibility": "known"
                }
            ]
        }
        with open(os.path.join(self.gameplay_dir, "status.json"), "w", encoding="utf-8") as f:
            json.dump(self.initial_status, f, indent=2)

        self.initial_status_md = "# Status\n- **XP**: 315 / 500\n- **Energy**: 100 / 100\n"
        with open(os.path.join(self.gameplay_dir, "status.md"), "w", encoding="utf-8") as f:
            f.write(self.initial_status_md)

        self.initial_items = {
            "campaign_id": "test_campaign",
            "purse": {"credits": 500, "display": "500 ₡"},
            "equipped": [{"name": "Multi-Spectrum Visor"}]
        }
        with open(os.path.join(self.gameplay_dir, "items.json"), "w", encoding="utf-8") as f:
            json.dump(self.initial_items, f, indent=2)

        self.initial_items_md = "# Items\n- **Current Coin**: `500 ₡`\n"
        with open(os.path.join(self.gameplay_dir, "items.md"), "w", encoding="utf-8") as f:
            f.write(self.initial_items_md)

        self.initial_relations = {
            "campaign_id": "test_campaign",
            "key_contacts": [{"name": "Handler Cross", "standing": "Professional"}]
        }
        with open(os.path.join(self.gameplay_dir, "relations.json"), "w", encoding="utf-8") as f:
            json.dump(self.initial_relations, f, indent=2)

        self.initial_relations_md = "# Relations\n- **Handler Cross**: Professional\n"
        with open(os.path.join(self.gameplay_dir, "relations.md"), "w", encoding="utf-8") as f:
            f.write(self.initial_relations_md)

        # Initial turn 1
        with open(os.path.join(self.turns_active_dir, "turn_0001.md"), "w", encoding="utf-8") as f:
            f.write("# Turn 1\nInitial briefing completed.\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _read_json(self, rel_path: str) -> dict:
        full = os.path.join(self.campaign_dir, rel_path)
        with open(full, "r", encoding="utf-8") as f:
            return json.load(f)

    def _read_text(self, rel_path: str) -> str:
        full = os.path.join(self.campaign_dir, rel_path)
        with open(full, "r", encoding="utf-8") as f:
            return f.read()

    # --- 1. Deterministic Transaction ID Tests ---

    def test_generate_transaction_id_determinism(self):
        tx_id_1 = TransactionManager.generate_transaction_id(2, "Accept Contract Alpha")
        tx_id_2 = TransactionManager.generate_transaction_id(2, "Accept Contract Alpha")
        tx_id_3 = TransactionManager.generate_transaction_id(2, "Accept Contract Alpha   ")
        self.assertEqual(tx_id_1, tx_id_2)
        self.assertEqual(tx_id_1, tx_id_3)
        self.assertTrue(tx_id_1.startswith("2_"))

    def test_generate_transaction_id_distinctness(self):
        id_action_a = TransactionManager.generate_transaction_id(2, "Accept Contract Alpha")
        id_action_b = TransactionManager.generate_transaction_id(2, "Accept Contract Beta")
        id_turn_3 = TransactionManager.generate_transaction_id(3, "Accept Contract Alpha")

        self.assertNotEqual(id_action_a, id_action_b)
        self.assertNotEqual(id_action_a, id_turn_3)

    # --- 2. Atomic Multi-File Staging and Commit Tests ---

    def test_staged_changes_applied_atomically_across_all_files(self):
        new_status = json.loads(json.dumps(self.initial_status))
        new_status["turn"] = 2
        new_status["progression"]["energy"] = 90
        new_status["purse"]["credits"] = 450
        new_status["purse"]["display"] = "450 ₡"

        new_items = json.loads(json.dumps(self.initial_items))
        new_items["purse"]["credits"] = 450
        new_items["equipped"].append({"name": "Encrypted Datapad"})

        new_relations = json.loads(json.dumps(self.initial_relations))
        new_relations["key_contacts"].append({"name": "Informant Jax", "standing": "Cautious"})

        tx_data = {
            "turn": 2,
            "action": "Infiltrate rooftop and meet Jax",
            "status.json": new_status,
            "status.md": "# Status\n- **Energy**: 90 / 100\n",
            "items.json": new_items,
            "items.md": "# Items\n- **Current Coin**: `450 ₡`\n",
            "relations.json": new_relations,
            "relations.md": "# Relations\n- **Handler Cross**: Professional\n- **Jax**: Cautious\n",
            "turn_file": "# Turn 2\nInfiltrated rooftop successfully.\n"
        }

        result = TransactionManager.commit(self.campaign_dir, tx_data)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "committed")
        self.assertEqual(result["turn"], 2)

        # Verify status.json
        disk_status = self._read_json("GAMEPLAY/status.json")
        self.assertEqual(disk_status["turn"], 2)
        self.assertEqual(disk_status["progression"]["energy"], 90)
        self.assertEqual(disk_status["purse"]["credits"], 450)
        self.assertIn("transaction_id", disk_status)
        self.assertEqual(disk_status["transaction_id"], result["transaction_id"])

        # Verify status.md
        disk_status_md = self._read_text("GAMEPLAY/status.md")
        self.assertIn("**Energy**: 90 / 100", disk_status_md)

        # Verify items.json and items.md
        disk_items = self._read_json("GAMEPLAY/items.json")
        self.assertEqual(len(disk_items["equipped"]), 2)
        disk_items_md = self._read_text("GAMEPLAY/items.md")
        self.assertIn("`450 ₡`", disk_items_md)

        # Verify relations.json and relations.md
        disk_relations = self._read_json("GAMEPLAY/relations.json")
        self.assertEqual(len(disk_relations["key_contacts"]), 2)
        disk_relations_md = self._read_text("GAMEPLAY/relations.md")
        self.assertIn("Jax", disk_relations_md)

        # Verify Turn 2 file was created
        turn_2_path = os.path.join(self.turns_active_dir, "turn_0002.md")
        self.assertTrue(os.path.exists(turn_2_path))
        self.assertIn("Infiltrated rooftop successfully.", self._read_text("TURNS/ACTIVE/turn_0002.md"))

        # Verify .transaction_log.json
        log = self._read_json(".transaction_log.json")
        self.assertIn(result["transaction_id"], log["transactions"])

    # --- 3. Rollback on Failure & State Preservation Tests ---

    def test_simulated_failure_during_commit_triggers_rollback(self):
        # Capture baseline content before transaction
        status_before = self._read_text("GAMEPLAY/status.json")
        status_md_before = self._read_text("GAMEPLAY/status.md")
        items_before = self._read_text("GAMEPLAY/items.json")
        items_md_before = self._read_text("GAMEPLAY/items.md")
        relations_before = self._read_text("GAMEPLAY/relations.json")
        relations_md_before = self._read_text("GAMEPLAY/relations.md")

        turn_2_path = os.path.join(self.turns_active_dir, "turn_0002.md")
        self.assertFalse(os.path.exists(turn_2_path))

        tm = TransactionManager(self.campaign_dir)
        mutated_status = json.loads(json.dumps(self.initial_status))
        mutated_status["turn"] = 2
        mutated_status["progression"]["energy"] = 10
        tm.stage("status.json", mutated_status)
        tm.stage("status.md", "# Mutated status\n- **Energy**: 10 / 100\n")
        tm.stage("items.md", "# Mutated items\n- **Current Coin**: `10 ₡`\n")
        tm.stage_turn(2, "Test Action", "Should rollback")

        # Simulate failure during commit
        with self.assertRaises(TransactionRollbackError):
            tm.commit(simulate_failure_at="during_commit")

        # Verify all files are restored to exact byte-for-byte pre-transaction state
        self.assertEqual(self._read_text("GAMEPLAY/status.json"), status_before)
        self.assertEqual(self._read_text("GAMEPLAY/status.md"), status_md_before)
        self.assertEqual(self._read_text("GAMEPLAY/items.json"), items_before)
        self.assertEqual(self._read_text("GAMEPLAY/items.md"), items_md_before)
        self.assertEqual(self._read_text("GAMEPLAY/relations.json"), relations_before)
        self.assertEqual(self._read_text("GAMEPLAY/relations.md"), relations_md_before)

        # Verify turn 2 file was NOT left on disk
        self.assertFalse(os.path.exists(turn_2_path))

        # Verify no .tmp files remain
        leftover_tmps = []
        for root, _, files in os.walk(self.campaign_dir):
            for file in files:
                if ".tmp" in file:
                    leftover_tmps.append(os.path.join(root, file))
        self.assertEqual(leftover_tmps, [])

    def test_simulated_mid_commit_failure_restores_replaced_files(self):
        status_before = self._read_text("GAMEPLAY/status.json")
        items_before = self._read_text("GAMEPLAY/items.json")
        turn_2_path = os.path.join(self.turns_active_dir, "turn_0002.md")

        mutated_status = json.loads(json.dumps(self.initial_status))
        mutated_status["turn"] = 2
        mutated_status["progression"]["energy"] = 5

        mutated_items = json.loads(json.dumps(self.initial_items))
        mutated_items["purse"]["credits"] = 0

        tm = TransactionManager(self.campaign_dir)
        tm.stage("status.json", mutated_status)
        tm.stage("items.json", mutated_items)
        tm.stage_turn(2, "Mid commit action", "Test")

        with self.assertRaises(TransactionRollbackError):
            tm.commit(simulate_failure_at="mid_commit")

        # Assert rollback restored status and items
        self.assertEqual(self._read_text("GAMEPLAY/status.json"), status_before)
        self.assertEqual(self._read_text("GAMEPLAY/items.json"), items_before)
        self.assertFalse(os.path.exists(turn_2_path))

    def test_pre_commit_validation_failure_prevents_file_writes(self):
        status_before = self._read_text("GAMEPLAY/status.json")

        bad_status = {
            "campaign_id": "test_campaign",
            "turn": 0  # Invalid turn (< 1)
        }

        tm = TransactionManager(self.campaign_dir)
        tm.stage("status.json", bad_status)

        with self.assertRaises(TransactionValidationError):
            tm.commit()

        # Files remain untouched
        self.assertEqual(self._read_text("GAMEPLAY/status.json"), status_before)

    # --- 4. Idempotency & Retry Safety Tests ---

    def test_idempotency_prevents_reapplying_deltas_and_duplicate_turns(self):
        action_text = "Inspect the terminal datapad"
        turn_number = 2

        mutated_status = json.loads(json.dumps(self.initial_status))
        mutated_status["turn"] = 2
        mutated_status["progression"]["energy"] = 85  # Decreased by 15
        mutated_status["purse"]["credits"] = 400

        tx_data = {
            "turn": turn_number,
            "action": action_text,
            "status.json": mutated_status,
            "items.md": "# Items\n- **Current Coin**: `400 ₡`\n",
            "turn_file": "# Turn 2\nInspected datapad.\n"
        }

        # 1. First commit: successful
        result1 = TransactionManager.commit(self.campaign_dir, tx_data)
        self.assertEqual(result1["status"], "committed")
        self.assertFalse(result1.get("idempotent", False))

        # Verify disk state after first commit
        status_after_first = self._read_json("GAMEPLAY/status.json")
        self.assertEqual(status_after_first["progression"]["energy"], 85)
        self.assertEqual(status_after_first["purse"]["credits"], 400)

        # Count active turn files
        active_turns_first = [f for f in os.listdir(self.turns_active_dir) if f.endswith(".md")]
        self.assertEqual(len(active_turns_first), 2)  # turn_0001.md and turn_0002.md

        # 2. Duplicate retry with same turn and action, but with rogue delta attempting further drop to 70
        rogue_retry_data = {
            "turn": turn_number,
            "action": action_text,
            "status.json": {
                **mutated_status,
                "progression": {**mutated_status["progression"], "energy": 70}
            },
            "turn_file": "# Turn 2 Duplicate\n"
        }

        result2 = TransactionManager.commit(self.campaign_dir, rogue_retry_data)
        self.assertTrue(result2["success"])
        self.assertEqual(result2["status"], "already_committed")
        self.assertTrue(result2["idempotent"])
        self.assertEqual(result2["transaction_id"], result1["transaction_id"])

        # 3. Assert energy did NOT decrease to 70; remained 85
        status_after_retry = self._read_json("GAMEPLAY/status.json")
        self.assertEqual(status_after_retry["progression"]["energy"], 85)
        self.assertEqual(status_after_retry["purse"]["credits"], 400)

        # 4. Assert turn files count did not change and content not corrupted
        active_turns_second = [f for f in os.listdir(self.turns_active_dir) if f.endswith(".md")]
        self.assertEqual(len(active_turns_second), 2)
        turn_2_content = self._read_text("TURNS/ACTIVE/turn_0002.md")
        self.assertIn("Inspected datapad.", turn_2_content)
        self.assertNotIn("Duplicate", turn_2_content)

    # --- 5. Decoupling Narration from Mutation Tests ---

    def test_decouple_narration_from_mutation_flow(self):
        gm_output = (
            "Alex successfully decrypts the datapad payload.\n"
            "[XP RESOLUTION: Previous: 315 | Delta: +25 (Decryption) | New Total: 340 / 500]\n"
            "[CURRENCY RESOLUTION: Previous: 500 ₡ | Delta: -50 | New Purse: 450 ₡]\n"
            "[SYS: Turn 2 | Initiate | XP 340/500 | Purse: 450 ₡ | Strain 3/100 | Checkpoints: 5/5]"
        )

        tm = TransactionManager(self.campaign_dir)
        # Narrator does not touch disk files; it passes output to TransactionManager
        result = tm.execute_narrative_turn(
            campaign_dir=self.campaign_dir,
            turn=2,
            action="Decrypt the datapad",
            gm_output=gm_output
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "committed")

        # Verify parsed state was committed to disk
        status = self._read_json("GAMEPLAY/status.json")
        self.assertEqual(status["turn"], 2)
        self.assertEqual(status["progression"]["xp"], 340)
        self.assertEqual(status["purse"]["credits"], 450)
        self.assertEqual(status["purse"]["display"], "450 ₡")
        self.assertEqual(status["progression"]["stress"], 3)

        # Verify items.md coin was mutated
        items_md = self._read_text("GAMEPLAY/items.md")
        self.assertIn("`450 ₡`", items_md)

        # Verify turn 2 file recorded both action and GM output
        turn_2 = self._read_text("TURNS/ACTIVE/turn_0002.md")
        self.assertIn("## Player Action\nDecrypt the datapad", turn_2)
        self.assertIn("Alex successfully decrypts the datapad payload.", turn_2)

    # --- 6. Object-Oriented Workflow & Helper Tests ---

    def test_object_oriented_workflow(self):
        tm = TransactionManager(self.campaign_dir)
        new_status = json.loads(json.dumps(self.initial_status))
        new_status["turn"] = 2

        tm.stage("status.json", new_status)
        tm.stage("status.md", "# Updated status md")
        tm.stage_turn(2, "Explore corridor", "Encountered a sentry drone.")

        self.assertIsNotNone(tm.get_staged("status.json"))
        self.assertIsNotNone(tm.get_staged("status.md"))

        res = tm.commit()
        self.assertTrue(res["success"])
        self.assertEqual(res["turn"], 2)
        self.assertEqual(len(tm.staged_files), 0)  # Cleaned up after commit

    def test_calling_conventions(self):
        # 1. tm.commit(tx_data) on instance with campaign_dir
        tm = TransactionManager(self.campaign_dir)
        tx_data = {
            "turn": 2,
            "action": "Action style test",
            "status.md": "# Status update style test"
        }
        res1 = tm.commit(tx_data)
        self.assertTrue(res1["success"])
        self.assertEqual(res1["turn"], 2)

        # 2. tm = TransactionManager() (without dir) then tm.commit(campaign_dir, tx_data)
        tm2 = TransactionManager()
        tx_data2 = {
            "turn": 3,
            "action": "Action style test 2",
            "status.md": "# Status update style test 2"
        }
        res2 = tm2.commit(self.campaign_dir, tx_data2)
        self.assertTrue(res2["success"])
        self.assertEqual(res2["turn"], 3)



if __name__ == "__main__":
    unittest.main()
