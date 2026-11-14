#!/usr/bin/env python3
"""
ENGINE/outcome.py
=================
Versioned, serializable Outcome object for deterministic turn resolution.
Carries effects, events, clocks_advanced, progression_delta, resources_delta,
offered_choices, next_state, and version.

Adheres strictly to Issue #14 R2: Must round-trip through JSON without loss.
"""

from dataclasses import dataclass, field, asdict
import json
from typing import Any, Dict, List, Optional


@dataclass
class Outcome:
    """
    Structured outcome of a single turn resolved by the deterministic core.
    """
    effects: List[Dict[str, Any]] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    clocks_advanced: List[Dict[str, Any]] = field(default_factory=list)
    progression_delta: Dict[str, Any] = field(default_factory=dict)
    resources_delta: Dict[str, Any] = field(default_factory=dict)
    offered_choices: List[Dict[str, Any]] = field(default_factory=list)
    next_state: Dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert Outcome to a dictionary with canonical key representation."""
        return {
            "version": self.version,
            "effects": self.effects,
            "events": self.events,
            "clocks_advanced": self.clocks_advanced,
            "progression_delta": self.progression_delta,
            "resources_delta": self.resources_delta,
            "offered_choices": self.offered_choices,
            "next_state": self.next_state,
        }

    def to_json(self, indent: Optional[int] = 2, sort_keys: bool = True) -> str:
        """
        Serialize to JSON string.
        Defaults to indent=2, sort_keys=True for canonical, byte-identical parity with JS.
        """
        return json.dumps(self.to_dict(), indent=indent, sort_keys=sort_keys, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Outcome":
        """Reconstruct Outcome from a dictionary."""
        return cls(
            effects=list(data.get("effects", [])),
            events=list(data.get("events", [])),
            clocks_advanced=list(data.get("clocks_advanced", [])),
            progression_delta=dict(data.get("progression_delta", {})),
            resources_delta=dict(data.get("resources_delta", {})),
            offered_choices=list(data.get("offered_choices", [])),
            next_state=dict(data.get("next_state", {})),
            version=int(data.get("version", 1)),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Outcome":
        """Reconstruct Outcome from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
