#!/usr/bin/env python3
"""
ENGINE/telemetry.py
===================
Telemetry & Observability Pipeline for Whimsy CYOA engine.
Provides structured JSONL event logging for narrative generation turns,
token budgets, latency, pacing dynamics, and style contract violations.

Stores logs in:
    CAMPAIGNS/<campaign_id>/GAMEPLAY/telemetry.jsonl
"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union

REQUIRED_TELEMETRY_FIELDS = [
    "timestamp",
    "campaign_id",
    "turn",
    "latency_ms",
    "model",
    "operational_mode",
    "zoom_level",
    "narrative_intensity",
    "prompt_tokens",
    "completion_tokens",
    "retrieval_hits",
    "style_violations",
    "outcome_state_delta"
]


def resolve_campaign_gameplay_dir(root_dir: str, campaign_id: str) -> str:
    """Resolves the GAMEPLAY directory for a given campaign."""
    cand = os.path.join(root_dir, "CAMPAIGNS", campaign_id, "GAMEPLAY")
    if os.path.isdir(os.path.dirname(cand)):
        return cand
    # Fallback if campaign_id is already a directory or path
    if os.path.isdir(campaign_id):
        return os.path.join(campaign_id, "GAMEPLAY")
    return cand


def resolve_telemetry_file_path(root_dir: str, campaign_id: str) -> str:
    """Returns absolute path to telemetry.jsonl for a campaign."""
    gameplay_dir = resolve_campaign_gameplay_dir(root_dir, campaign_id)
    return os.path.join(gameplay_dir, "telemetry.jsonl")


def validate_telemetry_record(record: Dict[str, Any]) -> List[str]:
    """
    Validates a telemetry record dictionary against required fields and types.
    Returns a list of validation error messages (empty list if valid).
    """
    errors = []
    if not isinstance(record, dict):
        return ["Record must be a dictionary"]

    for field in REQUIRED_TELEMETRY_FIELDS:
        if field not in record:
            errors.append(f"Missing required field: '{field}'")

    if "timestamp" in record and not isinstance(record["timestamp"], str):
        errors.append("Field 'timestamp' must be an ISO-8601 string")

    if "campaign_id" in record and not isinstance(record["campaign_id"], str):
        errors.append("Field 'campaign_id' must be a string")

    if "turn" in record and not isinstance(record["turn"], int):
        errors.append("Field 'turn' must be an integer")

    if "latency_ms" in record and not isinstance(record["latency_ms"], (int, float)):
        errors.append("Field 'latency_ms' must be a number")

    if "narrative_intensity" in record:
        val = record["narrative_intensity"]
        if not isinstance(val, int) or val < 1 or val > 5:
            errors.append("Field 'narrative_intensity' must be an integer between 1 and 5")

    if "prompt_tokens" in record and not isinstance(record["prompt_tokens"], int):
        errors.append("Field 'prompt_tokens' must be an integer")

    if "completion_tokens" in record and not isinstance(record["completion_tokens"], int):
        errors.append("Field 'completion_tokens' must be an integer")

    if "retrieval_hits" in record and not isinstance(record["retrieval_hits"], int):
        errors.append("Field 'retrieval_hits' must be an integer")

    if "style_violations" in record and not isinstance(record["style_violations"], list):
        errors.append("Field 'style_violations' must be a list")

    if "outcome_state_delta" in record and not isinstance(record["outcome_state_delta"], dict):
        errors.append("Field 'outcome_state_delta' must be a dictionary")

    return errors


def record_turn_telemetry(
    root_dir: str,
    campaign_id: str,
    turn: int,
    latency_ms: Union[int, float],
    model: str = "local-heuristic",
    operational_mode: str = "classic_cyoa",
    zoom_level: str = "detailed_scene",
    narrative_intensity: int = 1,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    retrieval_hits: int = 0,
    style_violations: Optional[List[Any]] = None,
    outcome_state_delta: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """
    Constructs and appends a structured telemetry event to CAMPAIGNS/<id>/GAMEPLAY/telemetry.jsonl.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    if style_violations is None:
        style_violations = []
    if outcome_state_delta is None:
        outcome_state_delta = {}

    record = {
        "timestamp": timestamp,
        "campaign_id": campaign_id,
        "turn": int(turn),
        "latency_ms": round(float(latency_ms), 2),
        "model": str(model),
        "operational_mode": str(operational_mode),
        "zoom_level": str(zoom_level),
        "narrative_intensity": int(narrative_intensity),
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "retrieval_hits": int(retrieval_hits),
        "style_violations": list(style_violations),
        "outcome_state_delta": dict(outcome_state_delta)
    }

    errors = validate_telemetry_record(record)
    if errors:
        raise ValueError(f"Telemetry record validation failed: {'; '.join(errors)}")

    file_path = resolve_telemetry_file_path(root_dir, campaign_id)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def read_campaign_telemetry(root_dir: str, campaign_id: str) -> List[Dict[str, Any]]:
    """Reads all parsed telemetry entries from a campaign's telemetry.jsonl."""
    file_path = resolve_telemetry_file_path(root_dir, campaign_id)
    if not os.path.exists(file_path):
        return []

    entries = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    entries.append(data)
            except json.JSONDecodeError:
                continue

    return entries


def get_campaign_telemetry_summary(root_dir: str, campaign_id: str) -> Dict[str, Any]:
    """
    Computes aggregated telemetry metrics across all logged turns for a campaign:
    - total_turns
    - avg_latency_ms
    - token_budgets (avg/total prompt and completion tokens)
    - pacing_distribution (zoom levels count/pct, avg intensity)
    - style_violation_frequency (total violations, violations per turn, category breakdowns)
    """
    records = read_campaign_telemetry(root_dir, campaign_id)
    total_turns = len(records)

    if total_turns == 0:
        return {
            "campaign_id": campaign_id,
            "total_turns": 0,
            "avg_latency_ms": 0.0,
            "token_budgets": {
                "avg_prompt_tokens": 0.0,
                "avg_completion_tokens": 0.0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0
            },
            "pacing_distribution": {
                "zoom_levels": {},
                "avg_narrative_intensity": 0.0
            },
            "style_violation_frequency": {
                "total_violations": 0,
                "turns_with_violations": 0,
                "violation_rate": 0.0,
                "categories": {}
            }
        }

    total_latency = sum(r.get("latency_ms", 0.0) for r in records)
    total_prompt_tokens = sum(r.get("prompt_tokens", 0) for r in records)
    total_comp_tokens = sum(r.get("completion_tokens", 0) for r in records)
    total_intensity = sum(r.get("narrative_intensity", 1) for r in records)

    zoom_counts: Dict[str, int] = {}
    total_style_violations = 0
    turns_with_violations = 0
    violation_categories: Dict[str, int] = {}

    for r in records:
        zoom = r.get("zoom_level", "unknown")
        zoom_counts[zoom] = zoom_counts.get(zoom, 0) + 1

        violations = r.get("style_violations", [])
        if violations:
            turns_with_violations += 1
            total_style_violations += len(violations)
            for v in violations:
                cat = "general"
                if isinstance(v, dict):
                    cat = v.get("category", v.get("rule", "general"))
                elif isinstance(v, str):
                    cat = v.split(":")[0].strip() if ":" in v else v
                violation_categories[cat] = violation_categories.get(cat, 0) + 1

    zoom_distribution = {}
    for z, count in zoom_counts.items():
        zoom_distribution[z] = {
            "count": count,
            "percentage": round((count / total_turns) * 100, 1)
        }

    return {
        "campaign_id": campaign_id,
        "total_turns": total_turns,
        "avg_latency_ms": round(total_latency / total_turns, 2),
        "token_budgets": {
            "avg_prompt_tokens": round(total_prompt_tokens / total_turns, 1),
            "avg_completion_tokens": round(total_comp_tokens / total_turns, 1),
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_comp_tokens
        },
        "pacing_distribution": {
            "zoom_levels": zoom_distribution,
            "avg_narrative_intensity": round(total_intensity / total_turns, 2)
        },
        "style_violation_frequency": {
            "total_violations": total_style_violations,
            "turns_with_violations": turns_with_violations,
            "violation_rate": round(total_style_violations / total_turns, 2),
            "categories": violation_categories
        }
    }
