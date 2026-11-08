#!/usr/bin/env python3
"""
Unit tests for schema validation.
Validates campaign_config.json, status.json, relations.json, items.json,
and world_foundation.json for the bundled template campaign against GLOBAL/SCHEMAS/*.
"""

import os
import sys
import json
import unittest
from typing import Any, List, Dict

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


class SimpleSchemaValidator:
    """
    Lightweight, dependency-free validator for JSON Schema subset used in CYOA schemas.
    Supports: type, required, properties, enum, minimum, maximum, items, additionalProperties.
    """

    @classmethod
    def validate(cls, data: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
        errors = []
        if not isinstance(schema, dict):
            return errors

        # 1. Type validation
        expected_type = schema.get("type")
        if expected_type:
            type_map = {
                "object": dict,
                "array": list,
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "null": type(None)
            }
            if expected_type == "integer" and isinstance(data, bool):
                errors.append(f"{path}: expected integer, got boolean")
            elif expected_type in type_map:
                target_cls = type_map[expected_type]
                if not isinstance(data, target_cls):
                    errors.append(f"{path}: expected {expected_type}, got {type(data).__name__}")
                    return errors  # Cannot validate deeper if base type mismatches

        # 2. Numeric range validation
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            if "minimum" in schema and data < schema["minimum"]:
                errors.append(f"{path}: {data} is less than minimum {schema['minimum']}")
            if "maximum" in schema and data > schema["maximum"]:
                errors.append(f"{path}: {data} is greater than maximum {schema['maximum']}")

        # 3. Enum validation
        if "enum" in schema:
            if data not in schema["enum"]:
                errors.append(f"{path}: value '{data}' not in enum {schema['enum']}")

        # 4. Object properties & required fields
        if isinstance(data, dict):
            required = schema.get("required", [])
            for req in required:
                if req not in data:
                    errors.append(f"{path}: missing required property '{req}'")

            properties = schema.get("properties", {})
            additional_props = schema.get("additionalProperties")
            for key, val in data.items():
                if key in properties:
                    errors.extend(cls.validate(val, properties[key], f"{path}.{key}"))
                elif isinstance(additional_props, dict):
                    errors.extend(cls.validate(val, additional_props, f"{path}.{key}"))
                elif additional_props is False:
                    errors.append(f"{path}: additional property '{key}' not allowed")

        # 5. Array items validation
        if isinstance(data, list) and "items" in schema:
            item_schema = schema["items"]
            for idx, item in enumerate(data):
                errors.extend(cls.validate(item, item_schema, f"{path}[{idx}]"))

        return errors


class TestSchemas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas_dir = os.path.join(ROOT_DIR, "GLOBAL", "SCHEMAS")
        with open(os.path.join(cls.schemas_dir, "campaign_init.schema.json"), "r") as f:
            cls.campaign_init_schema = json.load(f)
        with open(os.path.join(cls.schemas_dir, "turn_state.schema.json"), "r") as f:
            cls.turn_state_schema = json.load(f)
        with open(os.path.join(cls.schemas_dir, "world_foundation.schema.json"), "r") as f:
            cls.world_foundation_schema = json.load(f)
        with open(os.path.join(cls.schemas_dir, "outcome.schema.json"), "r") as f:
            cls.outcome_schema = json.load(f)

    def _load_json(self, rel_path: str) -> dict:
        full_path = os.path.join(ROOT_DIR, rel_path)
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # --- Campaign Init Schema Tests ---

    def test_template_campaign_config(self):
        config = self._load_json("CAMPAIGNS/template_campaign/campaign_config.json")
        errors = SimpleSchemaValidator.validate(config, self.campaign_init_schema)
        self.assertEqual(errors, [], f"Template campaign_config schema errors: {errors}")
        self.assertEqual(config["id"], "template_campaign")

    # --- Turn State Schema Tests ---

    def test_template_status_json(self):
        status = self._load_json("CAMPAIGNS/template_campaign/GAMEPLAY/status.json")
        errors = SimpleSchemaValidator.validate(status, self.turn_state_schema)
        self.assertEqual(errors, [], f"Template status.json schema errors: {errors}")
        self.assertEqual(status["campaign_id"], "template_campaign")
        self.assertGreaterEqual(status["turn"], 1)

    # --- World Foundation Schema Tests ---

    def test_template_world_foundation_json(self):
        wf = self._load_json("CAMPAIGNS/template_campaign/WORLD_FOUNDATION/world_foundation.json")
        errors = SimpleSchemaValidator.validate(wf, self.world_foundation_schema)
        self.assertEqual(errors, [], f"Template world_foundation schema errors: {errors}")
        self.assertEqual(wf["campaign_id"], "template_campaign")
    def test_pacing_state_schema_valid(self):
        status = self._load_json("CAMPAIGNS/template_campaign/GAMEPLAY/status.json")
        self.assertIn("pacing_state", status)
        pacing = status["pacing_state"]
        self.assertEqual(pacing["zoom_level"], "detailed_scene")
        self.assertEqual(pacing["narrative_intensity"], 1)
        self.assertEqual(pacing["elapsed_time_minutes"], 0)
        self.assertIn("scheduled_events", pacing)
        errors = SimpleSchemaValidator.validate(status, self.turn_state_schema)
        self.assertEqual(errors, [])

    # --- Relations and Items JSON Integrity Tests ---

    def test_template_relations_integrity(self):
        relations = self._load_json("CAMPAIGNS/template_campaign/GAMEPLAY/relations.json")
        self.assertEqual(relations.get("campaign_id"), "template_campaign")
        self.assertIn("key_contacts", relations)
        self.assertTrue(len(relations["key_contacts"]) > 0)
        for rel in relations["key_contacts"]:
            self.assertIn("name", rel)
            self.assertIn("standing", rel)

    def test_template_items_integrity(self):
        items = self._load_json("CAMPAIGNS/template_campaign/GAMEPLAY/items.json")
        self.assertEqual(items.get("campaign_id"), "template_campaign")
        self.assertIn("purse", items)
        self.assertIn("equipped", items)
        self.assertGreaterEqual(len(items["equipped"]), 1)
        for item in items["equipped"]:
            self.assertIn("name", item)

    # --- Negative Validation Tests ---

    def test_negative_invalid_config_missing_required(self):
        bad_config = {
            "id": "bad_campaign",
            "title": "Missing required properties"
        }
        errors = SimpleSchemaValidator.validate(bad_config, self.campaign_init_schema)
        self.assertTrue(any("missing required property" in e for e in errors))

    def test_negative_invalid_turn_state_negative_turn(self):
        bad_status = {
            "schema_version": 2,
            "campaign_id": "bad_campaign",
            "turn": 0,  # minimum is 1
            "timeline": "Cycle 0",
            "progression": {"checkpoint_tokens": 5, "checkpoint_max": 5},
            "scene_anchor": {"location": "Void", "context": "None", "time": "Never"},
            "public_state": {"flags": {}, "conditions": [], "open_threads": []},
            "clocks": []
        }
        errors = SimpleSchemaValidator.validate(bad_status, self.turn_state_schema)
        self.assertTrue(any("less than minimum" in e for e in errors))

    def test_negative_invalid_world_foundation_missing_required(self):
        bad_wf = {
            "campaign_id": "bad_campaign",
            "schema_version": "1.0.0"
        }
        errors = SimpleSchemaValidator.validate(bad_wf, self.world_foundation_schema)
        self.assertTrue(any("missing required property 'immutable_facts'" in e for e in errors))
        self.assertTrue(any("missing required property 'npc_knowledge'" in e for e in errors))
    def test_negative_invalid_pacing_zoom_level(self):
        bad_status = {
            "schema_version": 2,
            "campaign_id": "bad_campaign",
            "turn": 1,
            "timeline": "Cycle 1",
            "progression": {"checkpoint_tokens": 5, "checkpoint_max": 5},
            "scene_anchor": {"location": "Void", "context": "None", "time": "Never"},
            "public_state": {"flags": {}, "conditions": [], "open_threads": []},
            "clocks": [],
            "pacing_state": {
                "zoom_level": "instant_teleport_mode"
            }
        }
        errors = SimpleSchemaValidator.validate(bad_status, self.turn_state_schema)
        self.assertTrue(any("not in enum" in e for e in errors))

    def test_negative_invalid_pacing_intensity_out_of_range(self):
        bad_status = {
            "schema_version": 2,
            "campaign_id": "bad_campaign",
            "turn": 1,
            "timeline": "Cycle 1",
            "progression": {"checkpoint_tokens": 5, "checkpoint_max": 5},
            "scene_anchor": {"location": "Void", "context": "None", "time": "Never"},
            "public_state": {"flags": {}, "conditions": [], "open_threads": []},
            "clocks": [],
            "pacing_state": {
                "narrative_intensity": 6
            }
        }
        errors = SimpleSchemaValidator.validate(bad_status, self.turn_state_schema)
        self.assertTrue(any("greater than maximum" in e for e in errors))

    def test_negative_invalid_pacing_scheduled_event_missing_required(self):
        bad_status = {
            "schema_version": 2,
            "campaign_id": "bad_campaign",
            "turn": 1,
            "timeline": "Cycle 1",
            "progression": {"checkpoint_tokens": 5, "checkpoint_max": 5},
            "scene_anchor": {"location": "Void", "context": "None", "time": "Never"},
            "public_state": {"flags": {}, "conditions": [], "open_threads": []},
            "clocks": [],
            "pacing_state": {
                "scheduled_events": [
                    {"id": "missing_time"}
                ]
            }
        }
        errors = SimpleSchemaValidator.validate(bad_status, self.turn_state_schema)
        self.assertTrue(any("missing required property" in e for e in errors))

    # --- Outcome Schema Tests ---

    def test_outcome_schema_valid(self):
        valid_outcome = {
            "version": 1,
            "effects": [{"type": "stat_change", "target": "energy", "delta": -5}],
            "events": ["Clock filled: deadline"],
            "clocks_advanced": [{"id": "deadline", "delta": 1, "previous": 3, "current": 4, "max": 4, "fired": True}],
            "progression_delta": {"energy": -5},
            "resources_delta": {"credits": 50},
            "offered_choices": [{"index": 1, "text": "Continue onward"}],
            "next_state": {"turn": 2}
        }
        errors = SimpleSchemaValidator.validate(valid_outcome, self.outcome_schema)
        self.assertEqual(errors, [], f"Expected outcome to be valid, got: {errors}")

    def test_outcome_schema_missing_required_fails(self):
        invalid_outcome = {
            "version": 1,
            "effects": [],
            "events": []
        }
        errors = SimpleSchemaValidator.validate(invalid_outcome, self.outcome_schema)
        self.assertTrue(any("missing required property" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
