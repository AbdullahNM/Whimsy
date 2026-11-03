#!/usr/bin/env python3
"""
ENGINE/transaction_manager.py
=============================
Authoritative Two-Phase Transaction Manager & Atomic Committer for Narrative State.

Features:
- Deterministic transaction IDs based on turn number and action hash.
- Staging mutations across status, items, relations (JSON + MD), and turn logs.
- Two-phase commit with automatic rollback on error.
- Idempotency & retry safety via .transaction_log.json and status metadata.
- Decoupling of narration from state mutation.
"""

import os
import sys
import json
import hashlib
import copy
import glob
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Union

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.state_parser import StateParser


class TransactionError(Exception):
    """Base exception for all transaction errors."""
    pass


class TransactionValidationError(TransactionError):
    """Raised when validation of staged files fails prior to commit."""
    pass


class TransactionRollbackError(TransactionError):
    """Raised when commit fails and changes are rolled back."""
    pass


# Mapping friendly aliases to canonical paths relative to campaign_dir
FILE_KEY_MAPPING = {
    "status.json": "GAMEPLAY/status.json",
    "status_json": "GAMEPLAY/status.json",
    "status": "GAMEPLAY/status.json",
    "gameplay/status.json": "GAMEPLAY/status.json",

    "status.md": "GAMEPLAY/status.md",
    "status_md": "GAMEPLAY/status.md",
    "gameplay/status.md": "GAMEPLAY/status.md",

    "items.json": "GAMEPLAY/items.json",
    "items_json": "GAMEPLAY/items.json",
    "items": "GAMEPLAY/items.json",
    "gameplay/items.json": "GAMEPLAY/items.json",

    "items.md": "GAMEPLAY/items.md",
    "items_md": "GAMEPLAY/items.md",
    "gameplay/items.md": "GAMEPLAY/items.md",

    "relations.json": "GAMEPLAY/relations.json",
    "relations_json": "GAMEPLAY/relations.json",
    "relations": "GAMEPLAY/relations.json",
    "gameplay/relations.json": "GAMEPLAY/relations.json",

    "relations.md": "GAMEPLAY/relations.md",
    "relations_md": "GAMEPLAY/relations.md",
    "gameplay/relations.md": "GAMEPLAY/relations.md",
}


class TransactionManager:
    """
    Manages atomic turn state transactions across campaign files.
    """

    def __init__(self, campaign_dir: Optional[str] = None):
        self.campaign_dir = os.path.abspath(campaign_dir) if campaign_dir else None
        self.staged_files: Dict[str, Any] = {}
        self.current_turn: Optional[int] = None
        self.current_action: Optional[str] = None
        self.current_transaction_id: Optional[str] = None
        self.simulate_failure: bool = False
        self.simulate_failure_at: Optional[str] = None

    @staticmethod
    def generate_transaction_id(turn_number: int, action: str) -> str:
        """
        Generates a deterministic turn transaction ID based on turn number and action hash.
        Format: <turn_number>_<action_hash_12>
        """
        cleaned_action = (action or "").strip()
        action_hash = hashlib.sha256(cleaned_action.encode("utf-8")).hexdigest()[:12]
        return f"{turn_number}_{action_hash}"

    def stage(self, file_key: str, content: Any) -> str:
        """
        Stages an update for a canonical campaign file or turn markdown.
        Returns the resolved relative path.
        """
        key_lower = file_key.strip().replace("\\", "/").lower()

        if key_lower in FILE_KEY_MAPPING:
            canonical = FILE_KEY_MAPPING[key_lower]
        elif key_lower in ("turn_file", "turn_md", "turn", "turn.md"):
            if self.current_turn is not None:
                canonical = f"TURNS/ACTIVE/turn_{self.current_turn:04d}.md"
            else:
                canonical = "turn_file"
        else:
            canonical = os.path.normpath(file_key).replace("\\", "/")

        self.staged_files[canonical] = content
        return canonical

    def stage_files(self, files: Dict[str, Any]) -> None:
        """Stages multiple files at once from a dictionary."""
        for key, val in files.items():
            self.stage(key, val)

    def stage_turn(self, turn_number: int, player_input: str, gm_output: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Stages a new turn markdown file in TURNS/ACTIVE/turn_XXXX.md.
        """
        self.current_turn = turn_number
        self.current_action = player_input
        if not self.current_transaction_id:
            self.current_transaction_id = self.generate_transaction_id(turn_number, player_input)

        turn_file_rel = f"TURNS/ACTIVE/turn_{turn_number:04d}.md"
        content_lines = [
            f"# Turn {turn_number}",
            f"\n## Player Action\n{player_input}\n",
            f"## GM Response\n{gm_output}\n"
        ]
        if metadata:
            content_lines.append(f"## System State Delta\n```json\n{json.dumps(metadata, indent=2)}\n```\n")

        self.stage(turn_file_rel, "\n".join(content_lines))
        return turn_file_rel

    def get_staged(self, file_key: str) -> Optional[Any]:
        """Returns currently staged content for a given file key."""
        key_lower = file_key.strip().replace("\\", "/").lower()
        canonical = FILE_KEY_MAPPING.get(key_lower, os.path.normpath(file_key).replace("\\", "/"))
        return self.staged_files.get(canonical)

    def clear(self) -> None:
        """Clears all staged state and metadata."""
        self.staged_files.clear()
        self.current_turn = None
        self.current_action = None
        self.current_transaction_id = None
        self.simulate_failure = False
        self.simulate_failure_at = None

    def stage_mutations_from_narrative(
        self,
        campaign_dir: str,
        turn: int,
        action: str,
        gm_output: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Decouples narration from mutation.
        Parses GM output for state deltas and stages updates across status, items,
        and turn logs without modifying disk files directly.
        """
        campaign_dir = os.path.abspath(campaign_dir)
        self.campaign_dir = campaign_dir
        self.current_turn = turn
        self.current_action = action
        self.current_transaction_id = self.generate_transaction_id(turn, action)

        # 1. Read existing status.json
        status_json_path = os.path.join(campaign_dir, "GAMEPLAY", "status.json")
        status_json = {}
        if os.path.exists(status_json_path):
            with open(status_json_path, "r", encoding="utf-8") as f:
                status_json = json.load(f)

        # 2. Read existing status.md & items.md
        status_md_path = os.path.join(campaign_dir, "GAMEPLAY", "status.md")
        status_md = ""
        if os.path.exists(status_md_path):
            with open(status_md_path, "r", encoding="utf-8") as f:
                status_md = f.read()

        items_md_path = os.path.join(campaign_dir, "GAMEPLAY", "items.md")
        items_md = ""
        if os.path.exists(items_md_path):
            with open(items_md_path, "r", encoding="utf-8") as f:
                items_md = f.read()

        # 3. Parse deltas via StateParser
        new_status_md, new_items_md, _ = StateParser.apply_state_mutations(gm_output, status_md, items_md)
        new_status_json, _ = StateParser.apply_state_mutations_json(gm_output, status_json)

        new_status_json["turn"] = turn
        new_status_json["transaction_id"] = self.current_transaction_id

        # 4. Stage updates
        self.stage("status.json", new_status_json)
        if status_md:
            self.stage("status.md", new_status_md)
        if items_md:
            self.stage("items.md", new_items_md)

        # 5. Stage turn log
        self.stage_turn(turn, action, gm_output, metadata)

        return dict(self.staged_files)

    def execute_narrative_turn(
        self,
        campaign_dir: str,
        turn: int,
        action: str,
        gm_output: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        High-level wrapper: stages narrative turn resolution and executes atomic two-phase commit.
        """
        self.stage_mutations_from_narrative(campaign_dir, turn, action, gm_output, metadata)
        return self.commit(campaign_dir=campaign_dir, **kwargs)

    @classmethod
    def get_committed_transaction(
        cls,
        campaign_dir: str,
        transaction_id: Optional[str] = None,
        turn: Optional[int] = None,
        action: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Looks up whether a transaction has already been committed in .transaction_log.json or status.json.
        """
        campaign_dir = os.path.abspath(campaign_dir)
        log_path = os.path.join(campaign_dir, ".transaction_log.json")

        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    log_data = json.load(f)
                    transactions = log_data.get("transactions", {})

                    if transaction_id and transaction_id in transactions:
                        return transactions[transaction_id]

                    if turn is not None and action is not None:
                        calc_id = cls.generate_transaction_id(turn, action)
                        if calc_id in transactions:
                            return transactions[calc_id]

                        for tx in transactions.values():
                            if tx.get("turn") == turn and (tx.get("action") == action or tx.get("transaction_id") == calc_id):
                                return tx
            except Exception:
                pass

        # Fallback check in status.json
        status_path = os.path.join(campaign_dir, "GAMEPLAY", "status.json")
        if os.path.exists(status_path):
            try:
                with open(status_path, "r", encoding="utf-8") as f:
                    status_data = json.load(f)
                    stored_tx = status_data.get("transaction_id")
                    if transaction_id and stored_tx == transaction_id:
                        return {
                            "transaction_id": transaction_id,
                            "turn": status_data.get("turn"),
                            "files": ["GAMEPLAY/status.json"],
                            "result": status_data
                        }
                    if turn is not None and action is not None:
                        calc_id = cls.generate_transaction_id(turn, action)
                        if stored_tx == calc_id:
                            return {
                                "transaction_id": calc_id,
                                "turn": status_data.get("turn"),
                                "files": ["GAMEPLAY/status.json"],
                                "result": status_data
                            }
            except Exception:
                pass

        return None

    def validate_staged(self, campaign_dir: str) -> None:
        """
        Validates all staged data before commit:
        - Validates JSON parseability and structure
        - Validates status.json schema compliance if staged
        """
        # Validate status.json schema if present
        status_content = self.staged_files.get("GAMEPLAY/status.json")
        if status_content is not None:
            if isinstance(status_content, str):
                try:
                    status_dict = json.loads(status_content)
                except Exception as e:
                    raise TransactionValidationError(f"Invalid JSON in status.json: {e}")
            elif isinstance(status_content, dict):
                status_dict = status_content
            else:
                raise TransactionValidationError("status.json must be a dict or valid JSON string.")

            # Validate basic requirements
            required_keys = ["schema_version", "campaign_id", "turn", "timeline", "progression", "scene_anchor", "public_state", "clocks"]
            for req in required_keys:
                if req not in status_dict:
                    raise TransactionValidationError(f"status.json missing required property: '{req}'")

            if not isinstance(status_dict.get("turn"), int) or status_dict["turn"] < 1:
                raise TransactionValidationError(f"status.json turn must be an integer >= 1 (got {status_dict.get('turn')})")

            progression = status_dict.get("progression")
            if not isinstance(progression, dict) or "checkpoint_tokens" not in progression or "checkpoint_max" not in progression:
                raise TransactionValidationError("status.json progression must contain 'checkpoint_tokens' and 'checkpoint_max'")

            anchor = status_dict.get("scene_anchor")
            if not isinstance(anchor, dict) or not all(k in anchor for k in ("location", "context", "time")):
                raise TransactionValidationError("status.json scene_anchor must contain location, context, and time")

        # Validate other json files
        for path, content in self.staged_files.items():
            if path.endswith(".json") and path != "GAMEPLAY/status.json":
                if isinstance(content, str):
                    try:
                        json.loads(content)
                    except Exception as e:
                        raise TransactionValidationError(f"Invalid JSON in staged file {path}: {e}")

    @classmethod
    def _record_transaction_log(
        cls,
        campaign_dir: str,
        transaction_id: str,
        turn: Optional[int],
        action: Optional[str],
        committed_files: List[str]
    ) -> Dict[str, Any]:
        """
        Records the committed transaction into .transaction_log.json atomically.
        """
        log_path = os.path.join(campaign_dir, ".transaction_log.json")
        log_data = {"transactions": {}, "history": []}

        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict) and "transactions" in loaded:
                        log_data = loaded
            except Exception:
                pass

        record = {
            "transaction_id": transaction_id,
            "turn": turn,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "files": [os.path.relpath(f, campaign_dir).replace("\\", "/") for f in committed_files],
            "result": {
                "status": "committed",
                "transaction_id": transaction_id,
                "turn": turn
            }
        }

        log_data["transactions"][transaction_id] = record
        if transaction_id not in log_data.get("history", []):
            log_data.setdefault("history", []).append(transaction_id)

        # Bound history to recent 100 entries
        if len(log_data["history"]) > 100:
            to_remove = log_data["history"][:-100]
            log_data["history"] = log_data["history"][-100:]
            for old_id in to_remove:
                log_data["transactions"].pop(old_id, None)

        tmp_log = f"{log_path}.tmp"
        with open(tmp_log, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_log, log_path)

        return record

    @staticmethod
    def _rollback(
        backups: Dict[str, Any],
        created_files: set,
        tmp_files: List[str],
        committed_paths: List[str]
    ) -> None:
        """
        Rolls back all changes:
        - Cleans up .tmp files
        - Removes newly created files
        - Restores original pre-transaction contents for existing files
        """
        # 1. Clean up tmp files
        for tmp in tmp_files:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

        # 2. Delete newly created files
        for created in created_files:
            try:
                if os.path.exists(created):
                    os.remove(created)
            except Exception:
                pass

        # 3. Restore pre-existing files to exact original content
        for path, original_content in backups.items():
            try:
                if isinstance(original_content, bytes):
                    with open(path, "wb") as f:
                        f.write(original_content)
                else:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(original_content)
            except Exception:
                pass

    def execute_commit(
        self,
        campaign_dir: Optional[str] = None,
        transaction_data: Optional[Dict[str, Any]] = None,
        simulate_failure_at: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Internal implementation of atomic two-phase commit.
        """
        # Resolve campaign directory
        target_dir = campaign_dir or self.campaign_dir
        if not target_dir:
            raise ValueError("campaign_dir must be specified for commit.")
        target_dir = os.path.abspath(target_dir)

        # Ingest transaction_data if provided
        if transaction_data and isinstance(transaction_data, dict):
            if "turn" in transaction_data:
                self.current_turn = transaction_data["turn"]
            elif "turn_number" in transaction_data:
                self.current_turn = transaction_data["turn_number"]

            if "action" in transaction_data:
                self.current_action = transaction_data["action"]
            elif "player_input" in transaction_data:
                self.current_action = transaction_data["player_input"]

            if "transaction_id" in transaction_data:
                self.current_transaction_id = transaction_data["transaction_id"]

            # Staged files in nested dict
            staged = transaction_data.get("staged_files") or transaction_data.get("files")
            if isinstance(staged, dict):
                self.stage_files(staged)

            # Direct file keys in transaction_data
            for k, v in transaction_data.items():
                if k in ("turn", "turn_number", "action", "player_input", "transaction_id", "staged_files", "files", "metadata"):
                    continue
                k_lower = k.lower().replace("\\", "/")
                if k_lower in FILE_KEY_MAPPING or k.endswith(".json") or k.endswith(".md") or "turn" in k_lower:
                    self.stage(k, v)

        # Resolve transaction ID
        if not self.current_transaction_id:
            if self.current_turn is not None and self.current_action is not None:
                self.current_transaction_id = self.generate_transaction_id(self.current_turn, self.current_action)
            elif self.current_turn is not None:
                self.current_transaction_id = self.generate_transaction_id(self.current_turn, "")
            else:
                self.current_transaction_id = f"tx_{hashlib.sha256(str(id(self)).encode()).hexdigest()[:12]}"

        # Resolve generic "turn_file" alias if turn number is now known
        if "turn_file" in self.staged_files and self.current_turn is not None:
            content = self.staged_files.pop("turn_file")
            self.staged_files[f"TURNS/ACTIVE/turn_{self.current_turn:04d}.md"] = content

        # Check Idempotency & Retry safety
        existing = self.get_committed_transaction(
            target_dir,
            transaction_id=self.current_transaction_id,
            turn=self.current_turn,
            action=self.current_action
        )
        if existing:
            return {
                "success": True,
                "status": "already_committed",
                "idempotent": True,
                "transaction_id": existing.get("transaction_id", self.current_transaction_id),
                "turn": existing.get("turn", self.current_turn),
                "action": existing.get("action", self.current_action),
                "files_committed": existing.get("files", []),
                "result": existing.get("result", {}),
                "message": f"Transaction '{self.current_transaction_id}' already committed; state untouched."
            }

        # Inject transaction_id and turn into status.json if staged
        if "GAMEPLAY/status.json" in self.staged_files:
            status_val = self.staged_files["GAMEPLAY/status.json"]
            if isinstance(status_val, str):
                try:
                    status_val = json.loads(status_val)
                except Exception:
                    pass
            if isinstance(status_val, dict):
                status_val["transaction_id"] = self.current_transaction_id
                if self.current_turn is not None:
                    status_val["turn"] = self.current_turn
                self.staged_files["GAMEPLAY/status.json"] = status_val

        # Pre-commit Validation
        self.validate_staged(target_dir)

        # Prepare Two-Phase Commit structures
        sim_fail = simulate_failure_at or self.simulate_failure_at
        if self.simulate_failure and not sim_fail:
            sim_fail = "during_commit"

        backups: Dict[str, Any] = {}
        created_files = set()
        tmp_files: List[str] = []
        prepared_pairs: List[Tuple[str, str]] = []  # (target_path, tmp_path)
        committed_target_paths: List[str] = []

        try:
            # === PHASE 1: PREPARE ===
            for rel_path, content in self.staged_files.items():
                abs_target = os.path.normpath(os.path.join(target_dir, rel_path))

                # Security check: ensure path is within target_dir
                common = os.path.commonpath([target_dir, abs_target])
                if common != target_dir:
                    raise TransactionError(f"Security: attempt to modify file outside campaign directory: {rel_path}")

                os.makedirs(os.path.dirname(abs_target), exist_ok=True)

                if os.path.exists(abs_target):
                    with open(abs_target, "rb") as f:
                        backups[abs_target] = f.read()
                else:
                    created_files.add(abs_target)

                # Write staged content to temporary file
                tmp_path = f"{abs_target}.tmp.{self.current_transaction_id}"
                tmp_files.append(tmp_path)

                if isinstance(content, (dict, list)):
                    serialized = json.dumps(content, indent=2, ensure_ascii=False)
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        f.write(serialized)
                elif isinstance(content, bytes):
                    with open(tmp_path, "wb") as f:
                        f.write(content)
                else:
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        f.write(str(content))

                prepared_pairs.append((abs_target, tmp_path))

            # Simulated failure hook before file replaces
            if sim_fail in ("during_commit", "pre_commit", "prepare"):
                raise RuntimeError(f"Simulated failure at {sim_fail}")

            # === PHASE 2: COMMIT ===
            for idx, (target_path, tmp_path) in enumerate(prepared_pairs):
                if sim_fail == "mid_commit" and idx > 0:
                    raise RuntimeError("Simulated failure mid-commit")

                os.replace(tmp_path, target_path)
                committed_target_paths.append(target_path)

            if sim_fail == "post_replace":
                raise RuntimeError("Simulated failure post-replace")

            # Record to .transaction_log.json
            tx_record = self._record_transaction_log(
                target_dir,
                self.current_transaction_id,
                self.current_turn,
                self.current_action,
                committed_target_paths
            )

        except Exception as e:
            # Atomic rollback on any failure
            self._rollback(backups, created_files, tmp_files, committed_target_paths)
            if isinstance(e, TransactionError):
                raise
            raise TransactionRollbackError(f"Commit failed and was rolled back: {e}") from e

        # Success: clean up staging area
        self.clear()

        return {
            "success": True,
            "status": "committed",
            "transaction_id": tx_record["transaction_id"],
            "turn": tx_record.get("turn"),
            "action": tx_record.get("action"),
            "files_committed": tx_record.get("files", []),
            "result": tx_record.get("result", {})
        }


class _CommitDescriptor:
    """Descriptor enabling commit to be called as either TransactionManager.commit(...) or tm.commit(...)."""
    def __get__(self, instance, owner):
        if instance is None:
            def _class_commit(campaign_dir: str, transaction_data: Optional[Dict[str, Any]] = None, **kwargs):
                if isinstance(campaign_dir, dict) and transaction_data is None:
                    raise ValueError("campaign_dir must be a string path when calling TransactionManager.commit")
                tm = owner(campaign_dir)
                return tm.execute_commit(campaign_dir=campaign_dir, transaction_data=transaction_data, **kwargs)
            return _class_commit
        else:
            def _instance_commit(campaign_dir: Optional[Union[str, Dict[str, Any]]] = None, transaction_data: Optional[Dict[str, Any]] = None, **kwargs):
                target_dir = instance.campaign_dir
                if isinstance(campaign_dir, str):
                    target_dir = campaign_dir
                elif isinstance(campaign_dir, dict) and transaction_data is None:
                    transaction_data = campaign_dir

                return instance.execute_commit(campaign_dir=target_dir, transaction_data=transaction_data, **kwargs)
            return _instance_commit


TransactionManager.commit = _CommitDescriptor()

