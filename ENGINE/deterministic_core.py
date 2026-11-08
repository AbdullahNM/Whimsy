#!/usr/bin/env python3
"""
ENGINE/deterministic_core.py
============================
Pure functional turn resolution engine for the Antigravity CYOA Engine.
Exposes Core.resolve(state, action, config=None, rng=None).

Guarantees:
- Zero network access
- Zero filesystem reads or writes
- Deterministic seeded PRNG (Mulberry32)
- Strict action validation as a precondition (R7)
- Byte-identical parity with UI/core/deterministic_core.js (R4, R5)
"""

import copy
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from ENGINE.outcome import Outcome


class ActionValidationError(ValueError):
    """Raised when an action is invalid under the active operational mode."""
    pass


class TransitionRejectedError(ValueError):
    """Raised when a narrative transition violates anti-degradation pacing gates."""
    pass


class SeededRNG:
    """
    Portable 32-bit PRNG (Mulberry32) for cross-language determinism with JS.
    """
    def __init__(self, seed: int = 0):
        self.state = int(seed) & 0xFFFFFFFF

    def next(self) -> float:
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 15)) * (z | 1)) & 0xFFFFFFFF
        z = (z ^ (z + (((z ^ (z >> 7)) * (z | 61)) & 0xFFFFFFFF))) & 0xFFFFFFFF
        return ((z ^ (z >> 14)) & 0xFFFFFFFF) / 4294967296.0

    def randint(self, a: int, b: int) -> int:
        return a + int(self.next() * (b - a + 1))


# Supported Zoom Levels
ZOOM_DETAILED_SCENE = "detailed_scene"
ZOOM_SHORT_SUMMARY = "short_summary"
ZOOM_MONTAGE = "montage"
ZOOM_TIME_SKIP = "time_skip"
VALID_ZOOM_LEVELS = [ZOOM_DETAILED_SCENE, ZOOM_SHORT_SUMMARY, ZOOM_MONTAGE, ZOOM_TIME_SKIP]

# Default fallback choices
DEFAULT_FALLBACK_CHOICES = [
    {
        "index": 1,
        "text": "Press forward along your primary path."
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


class Core:
    """
    Pure headless deterministic CYOA turn resolution engine.
    """

    @classmethod
    def resolve(
        cls,
        state: Dict[str, Any],
        action: Union[str, int, Dict[str, Any]],
        config: Optional[Dict[str, Any]] = None,
        rng: Optional[Union[SeededRNG, int]] = None
    ) -> Outcome:
        """
        Pure function resolving one turn.
        Preconditions:
        - Mode-dependent action validation
        - Transition gate validation

        Returns an Outcome carrying all effects, events, clocks_advanced,
        progression_delta, resources_delta, offered_choices, and next_state.
        """
        if not isinstance(state, dict):
            raise ValueError("state must be a dictionary")

        config = config or {}

        # Initialize deterministic RNG
        if rng is None:
            seed = config.get("seed", 42)
            rng_inst = SeededRNG(seed)
        elif isinstance(rng, (int, float)):
            rng_inst = SeededRNG(int(rng))
        else:
            rng_inst = rng

        # -------------------------------------------------------------
        # STEP 1: Action Validation (Precondition - R7)
        # -------------------------------------------------------------
        is_valid, err_msg, parsed_action = cls.validate_action(state, action, config)
        if not is_valid:
            raise ActionValidationError(err_msg)

        mode = parsed_action.get("mode", "classic_cyoa")
        selected_index = parsed_action.get("index")
        action_text = parsed_action.get("text", str(action))

        # -------------------------------------------------------------
        # STEP 2: Transition Gate Validation (Precondition)
        # -------------------------------------------------------------
        pacing_state = copy.deepcopy(state.get("pacing_state") or {})
        proposed_zoom = config.get("proposed_zoom") or cls.evaluate_focus(action_text, pacing_state)
        proposed_intensity = config.get("proposed_intensity")
        if proposed_intensity is None:
            proposed_intensity = cls.recommend_intensity(action_text, pacing_state)
        else:
            proposed_intensity = int(proposed_intensity)

        proposed_time_skip = int(config.get("proposed_time_skip_minutes", 0))
        proposed_location = config.get("proposed_location")
        causal_justification = bool(config.get("causal_justification", False))
        explicit_permission = bool(config.get("explicit_permission", False))

        is_trans_valid, trans_reason = cls.validate_transition(
            pacing_state=pacing_state,
            action_text=action_text,
            proposed_zoom=proposed_zoom,
            proposed_time_skip_minutes=proposed_time_skip,
            proposed_intensity=proposed_intensity,
            proposed_location=proposed_location,
            causal_justification=causal_justification,
            explicit_permission=explicit_permission
        )
        if not is_trans_valid:
            raise TransitionRejectedError(trans_reason)

        # -------------------------------------------------------------
        # STEP 3: Rule Evaluation & Mechanical Mutation Resolution
        # -------------------------------------------------------------
        rules = config.get("rules", [])
        matched_rule = cls._match_rule(rules, selected_index, action_text)

        effects: List[Dict[str, Any]] = []
        events: List[str] = []
        clocks_advanced: List[Dict[str, Any]] = []

        if matched_rule:
            progression_delta = dict(matched_rule.get("progression_delta", {}))
            resources_delta = dict(matched_rule.get("resources_delta", {}))
            rule_clocks = list(matched_rule.get("clocks_advanced", []))
            rule_events = list(matched_rule.get("events", []))
            events.extend(rule_events)
            flags_to_set = dict(matched_rule.get("flags", {}))
            time_delta = int(matched_rule.get("time_delta_minutes", 10))
            zoom_level = matched_rule.get("zoom_level", proposed_zoom)
            narrative_intensity = int(matched_rule.get("narrative_intensity", proposed_intensity))
            next_location = matched_rule.get("location")
            next_context = matched_rule.get("context")
            rule_next_choices = matched_rule.get("next_choices")
        else:
            # Standard deterministic CYOA baseline mechanics
            progression_delta = {}
            resources_delta = {}
            rule_clocks = []
            flags_to_set = {}
            next_location = proposed_location
            next_context = None
            rule_next_choices = None
            zoom_level = proposed_zoom
            narrative_intensity = proposed_intensity

            if proposed_time_skip > 0:
                time_delta = proposed_time_skip
            elif proposed_zoom == ZOOM_TIME_SKIP:
                time_delta = 480
            elif proposed_zoom == ZOOM_MONTAGE:
                time_delta = 1440
            elif selected_index == 4:
                time_delta = 60
            elif selected_index in (2, 3):
                time_delta = 15
            elif proposed_zoom == ZOOM_SHORT_SUMMARY:
                time_delta = 30
            else:
                time_delta = 10

            if selected_index == 1:
                zoom_level = proposed_zoom if config.get("proposed_zoom") else ZOOM_DETAILED_SCENE
                narrative_intensity = proposed_intensity if config.get("proposed_intensity") is not None else 2
                if "energy" in state.get("progression", {}):
                    progression_delta["energy"] = -5
                flags_to_set["path_pressed"] = True
                rule_clocks.append({"id": "contract_deadline", "delta": 1})
            elif selected_index == 2:
                zoom_level = proposed_zoom if config.get("proposed_zoom") else ZOOM_DETAILED_SCENE
                narrative_intensity = proposed_intensity if config.get("proposed_intensity") is not None else 1
                if "energy" in state.get("progression", {}):
                    progression_delta["energy"] = -5
                if "stress" in state.get("progression", {}):
                    progression_delta["stress"] = 2
                flags_to_set["inspected_area"] = True
            elif selected_index == 3:
                zoom_level = proposed_zoom if config.get("proposed_zoom") else ZOOM_DETAILED_SCENE
                narrative_intensity = proposed_intensity if config.get("proposed_intensity") is not None else 1
                if "stress" in state.get("progression", {}):
                    progression_delta["stress"] = -5
                flags_to_set["conferred_with_companions"] = True
            elif selected_index == 4:
                zoom_level = proposed_zoom if config.get("proposed_zoom") else ZOOM_SHORT_SUMMARY
                narrative_intensity = proposed_intensity if config.get("proposed_intensity") is not None else 1
                if "energy" in state.get("progression", {}):
                    progression_delta["energy"] = 25
                if "stress" in state.get("progression", {}):
                    progression_delta["stress"] = -15
                flags_to_set["rested"] = True
                rule_clocks.append({"id": "contract_deadline", "delta": 1})

        # Clone state to construct next_state
        next_state = copy.deepcopy(state)
        current_turn = int(state.get("turn", 1))
        next_turn = current_turn + 1
        next_state["turn"] = next_turn
        effects.append({
            "type": "turn_advance",
            "previous": current_turn,
            "current": next_turn
        })

        # Apply progression mutations
        if progression_delta:
            next_progression = next_state.setdefault("progression", {})
            for key, delta in sorted(progression_delta.items()):
                if key in next_progression:
                    old_val = next_progression[key]
                    max_key = f"{key}_max"
                    max_val = next_progression.get(max_key)
                    new_val = old_val + delta
                    if max_val is not None and isinstance(max_val, (int, float)):
                        new_val = min(max_val, new_val)
                    new_val = max(0, new_val)
                    next_progression[key] = new_val
                    effects.append({
                        "type": "stat_change",
                        "target": f"progression.{key}",
                        "delta": delta,
                        "previous": old_val,
                        "current": new_val
                    })

        # Apply resources mutations
        if resources_delta:
            next_purse = next_state.setdefault("purse", {})
            for key, delta in sorted(resources_delta.items()):
                if key in next_purse and isinstance(next_purse[key], (int, float)):
                    old_val = next_purse[key]
                    new_val = max(0, old_val + delta)
                    next_purse[key] = new_val
                    effects.append({
                        "type": "resource_change",
                        "target": f"purse.{key}",
                        "delta": delta,
                        "previous": old_val,
                        "current": new_val
                    })

            # Update display string if credits or coins are tracked
            if "credits" in next_purse:
                next_purse["display"] = f"{next_purse['credits']} ₡"
            elif any(c in next_purse for c in ("gold", "silver", "copper")):
                g = next_purse.get("gold", 0)
                s = next_purse.get("silver", 0)
                c = next_purse.get("copper", 0)
                next_purse["display"] = f"{g}G {s}S {c}C"

        # Apply flags
        if flags_to_set:
            next_flags = next_state.setdefault("public_state", {}).setdefault("flags", {})
            for k, v in sorted(flags_to_set.items()):
                next_flags[k] = v
                effects.append({
                    "type": "flag_set",
                    "target": f"public_state.flags.{k}",
                    "value": v
                })

        # Apply Clocks
        clocks_list = next_state.setdefault("clocks", [])
        clock_map = {c.get("id"): c for c in clocks_list if "id" in c}

        # Check explicit rule/choice clocks
        for rc in rule_clocks:
            cid = rc.get("id")
            cdelta = int(rc.get("delta", 1))
            if cid in clock_map:
                c = clock_map[cid]
                old_val = int(c.get("current", 0))
                max_val = int(c.get("max", 4))
                new_val = min(max_val, old_val + cdelta)
                c["current"] = new_val
                fired = (new_val >= max_val)
                clocks_advanced.append({
                    "id": cid,
                    "label": c.get("label", cid),
                    "delta": cdelta,
                    "previous": old_val,
                    "current": new_val,
                    "max": max_val,
                    "fired": fired
                })
                effects.append({
                    "type": "clock_advance",
                    "target": f"clocks.{cid}",
                    "delta": cdelta,
                    "previous": old_val,
                    "current": new_val,
                    "max": max_val
                })
                if fired and old_val < max_val:
                    events.append(f"Clock filled: {c.get('label', cid)}")

        # Advance Time and Pacing State
        pacing = next_state.setdefault("pacing_state", {})
        start_min = int(pacing.get("elapsed_time_minutes", 0))
        end_min = start_min + time_delta
        pacing["elapsed_time_minutes"] = end_min
        pacing["zoom_level"] = zoom_level
        pacing["narrative_intensity"] = narrative_intensity

        old_stamp = pacing.get("timeline_stamp", "Day 1, 08:00")
        new_stamp = cls.advance_timeline_stamp(old_stamp, start_min, end_min, time_delta)
        pacing["timeline_stamp"] = new_stamp

        if next_location:
            pacing["current_location"] = next_location
            next_state.setdefault("scene_anchor", {})["location"] = next_location

        if next_context:
            next_state.setdefault("scene_anchor", {})["context"] = next_context

        effects.append({
            "type": "time_advance",
            "delta_minutes": time_delta,
            "timeline_stamp": new_stamp
        })

        # Check scheduled events crossed
        scheduled = pacing.get("scheduled_events", [])
        for evt in scheduled:
            tt = int(evt.get("trigger_time_minutes", 0))
            fired = bool(evt.get("fired", False))
            if not fired:
                if start_min < tt <= end_min or (start_min == 0 and tt == 0):
                    evt["fired"] = True
                    events.append(f"Scheduled event triggered: {evt.get('description', evt.get('id'))}")

        # Offered choices for subsequent turn
        if rule_next_choices:
            next_choices = [dict(c) for c in rule_next_choices]
        else:
            next_choices = [
                {
                    "index": 1,
                    "text": "Press forward along your primary path."
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

        next_state["offered_choices"] = next_choices

        return Outcome(
            version=1,
            effects=effects,
            events=events,
            clocks_advanced=clocks_advanced,
            progression_delta=progression_delta,
            resources_delta=resources_delta,
            offered_choices=next_choices,
            next_state=next_state
        )

    # -------------------------------------------------------------------------
    # Action Validation (Precondition)
    # -------------------------------------------------------------------------

    @classmethod
    def validate_action(
        cls,
        state: Dict[str, Any],
        action: Union[str, int, Dict[str, Any]],
        config: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Deterministically validates player action against the operational mode.
        Returns (is_valid: bool, error_msg: str, parsed_action: dict).
        """
        if action is None:
            return False, "Action input cannot be empty.", {}

        clean_str = str(action).strip()
        if not clean_str:
            return False, "Action input cannot be empty.", {}

        config = config or {}
        mode = (
            config.get("operational_mode")
            or state.get("operational_mode")
            or config.get("mode")
            or "classic_cyoa"
        )
        if mode not in ["classic_cyoa", "freeform_simulation"]:
            mode = "classic_cyoa"

        # Freeform Simulation Mode
        if mode == "freeform_simulation":
            return True, "", {
                "index": None,
                "text": clean_str,
                "raw_input": action,
                "mode": "freeform_simulation"
            }

        # Classic CYOA Mode
        offered_choices = (
            state.get("offered_choices")
            or config.get("offered_choices")
            or config.get("choices")
            or DEFAULT_FALLBACK_CHOICES
        )

        choice_map = {c["index"]: c for c in offered_choices if "index" in c}
        if not choice_map:
            for idx, c in enumerate(DEFAULT_FALLBACK_CHOICES, start=1):
                choice_map[idx] = c
            offered_choices = list(DEFAULT_FALLBACK_CHOICES)

        min_idx = min(choice_map.keys())
        max_idx = max(choice_map.keys())

        # 1. Compound action rejection
        multi_pattern = re.compile(
            r'^(?:option\s+|choice\s+)?(\d+)\s*(?:,|&|\band\b|\+|(?:and\s+)?then)\s*(?:option\s+|choice\s+)?(\d+)',
            re.IGNORECASE
        )
        if multi_pattern.search(clean_str):
            return False, "Compound actions are not permitted in Classic CYOA mode. Please select a single offered option.", {}

        chained_pattern = re.compile(
            r'^(?:(?:option|choice)\s+)?\d+\s*[\.\)]?\s*(?:and\s+then|then|and|&|,|;|followed\s+by|\+)\s+(.+)$',
            re.IGNORECASE
        )
        if chained_pattern.match(clean_str):
            return False, "Compound actions are not permitted in Classic CYOA mode. Please select a single offered option.", {}

        if re.search(r'\b(?:and\s+then|then\s+also|followed\s+by)\b', clean_str, re.IGNORECASE):
            return False, "Compound actions are not permitted in Classic CYOA mode. Please select a single offered option.", {}

        # 2. Pure single integer
        m_int = re.fullmatch(r'(\d+)', clean_str)
        if m_int:
            idx = int(m_int.group(1))
            if idx in choice_map:
                return True, "", {
                    "index": idx,
                    "text": choice_map[idx]["text"],
                    "raw_input": action,
                    "mode": "classic_cyoa"
                }
            return False, f"Option {idx} is out of range. Valid options are {min_idx} to {max_idx}.", {}

        # 3. Option or Choice prefix
        m_opt = re.fullmatch(r'(?:option|choice)\s+(\d+)[\.\)]?', clean_str, re.IGNORECASE)
        if m_opt:
            idx = int(m_opt.group(1))
            if idx in choice_map:
                return True, "", {
                    "index": idx,
                    "text": choice_map[idx]["text"],
                    "raw_input": action,
                    "mode": "classic_cyoa"
                }
            return False, f"Option {idx} is out of range. Valid options are {min_idx} to {max_idx}.", {}

        # 4. Numbered prefix line, e.g. "1. Press forward..."
        m_prefix = re.match(r'^(\d+)[\.\)]\s*(.*)$', clean_str)
        if m_prefix:
            idx = int(m_prefix.group(1))
            tail = m_prefix.group(2).strip()
            if idx in choice_map:
                if not tail or cls._matches_choice_text(tail, choice_map[idx]["text"]):
                    return True, "", {
                        "index": idx,
                        "text": choice_map[idx]["text"],
                        "raw_input": action,
                        "mode": "classic_cyoa"
                    }

        # 5. Semantic text match against offered choices
        for idx, choice in sorted(choice_map.items()):
            target_text = choice.get("text", "")
            if cls._matches_choice_text(clean_str, target_text):
                return True, "", {
                    "index": idx,
                    "text": target_text,
                    "raw_input": action,
                    "mode": "classic_cyoa"
                }

        return False, "Arbitrary freeform actions are not permitted in Classic CYOA mode. Please select one of the offered numbered options.", {}

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        if not text:
            return ""
        no_brackets = re.sub(r'\[.*?\]', '', text)
        cleaned = re.sub(r'[^\w\s]', ' ', no_brackets.lower())
        return ' '.join(cleaned.split())

    @classmethod
    def _matches_choice_text(cls, candidate: str, target: str) -> bool:
        norm_cand = cls._normalize_text(candidate)
        norm_target = cls._normalize_text(target)
        if not norm_cand or not norm_target:
            return False
        if norm_cand == norm_target:
            return True

        parts = re.split(r'[:\-–—]', target, maxsplit=1)
        if len(parts) > 1:
            norm_title = cls._normalize_text(parts[0])
            if norm_cand == norm_title:
                return True

        if len(norm_cand) >= 15 and norm_target.startswith(norm_cand):
            return True

        return False

    # -------------------------------------------------------------------------
    # Transition Validation (Precondition)
    # -------------------------------------------------------------------------

    @classmethod
    def validate_transition(
        cls,
        pacing_state: Dict[str, Any],
        action_text: str,
        proposed_zoom: str,
        proposed_time_skip_minutes: int,
        proposed_intensity: int,
        proposed_location: Optional[str] = None,
        causal_justification: bool = False,
        explicit_permission: bool = False,
    ) -> Tuple[bool, str]:
        """
        Validates proposed narrative transitions against anti-degradation gates.
        """
        pacing = pacing_state or {}
        curr_zoom = pacing.get("zoom_level", ZOOM_DETAILED_SCENE)
        curr_intensity = int(pacing.get("narrative_intensity", 1))

        if proposed_zoom not in VALID_ZOOM_LEVELS:
            return False, f"Proposed zoom level '{proposed_zoom}' is invalid. Allowed: {VALID_ZOOM_LEVELS}"

        # Unresolved intentions gate: no unearned time skips
        unresolved = pacing.get("unresolved_intentions", [])
        if unresolved and not explicit_permission and not causal_justification:
            if proposed_time_skip_minutes > 0 or proposed_zoom == ZOOM_TIME_SKIP:
                return False, (
                    f"Transition blocked: Scene has unresolved intentions ({unresolved}). "
                    f"Time skips and scene departures require explicit player resolution or causal justification."
                )

        # Dramatic escalation gate: narrative intensity cannot jump > 2 levels without causal justification
        if (proposed_intensity - curr_intensity) > 2 and not causal_justification:
            return False, (
                f"Transition blocked: Dramatic escalation from intensity {curr_intensity} to {proposed_intensity} "
                f"exceeds the 2-step maximum without causal justification."
            )

        # Location jump gate: instantaneous relocation requires travel action or justification
        curr_loc = pacing.get("current_location")
        if proposed_location and curr_loc and proposed_location != curr_loc:
            has_conflicts = len(pacing.get("active_conflicts", [])) > 0
            if (has_conflicts or unresolved) and not causal_justification and not explicit_permission:
                action_lower = action_text.lower()
                travel_terms = ["travel", "journey", "walk", "ride", "fly", "sail", "transit", "head to", "move to"]
                if not any(t in action_lower for t in travel_terms):
                    return False, (
                        f"Transition blocked: Cannot jump location from '{curr_loc}' to '{proposed_location}' "
                        f"while active intentions or conflicts remain without travel action or causal justification."
                    )

        return True, "Transition approved."

    # -------------------------------------------------------------------------
    # Pacing and Focus Heuristics
    # -------------------------------------------------------------------------

    @classmethod
    def evaluate_focus(cls, action_text: str, pacing_state: Optional[Dict[str, Any]] = None) -> str:
        """Determines appropriate zoom level from action keywords."""
        text = (action_text or "").lower().strip()

        # Detailed scene cues
        detailed_cues = [
            r"\bzoom in\b", r"\belaborate\b", r"\bin detail\b", r"\bin full detail\b",
            r"\bfocus on\b", r"\bstep by step\b", r"\bexamine closely\b", r"\blook closely\b",
            r"\btake my time\b", r"\bslow down\b", r"\bplay out\b", r"\bdetailed scene\b"
        ]
        if any(re.search(p, text) for p in detailed_cues):
            return ZOOM_DETAILED_SCENE

        # Time skip cues
        time_skip_cues = [
            r"\bskip to\b", r"\btime skip\b", r"\bskip ahead\b", r"\bfast forward\b",
            r"\bjump ahead\b", r"\bwait until morning\b", r"\bsleep until\b",
            r"\buntil tomorrow\b", r"\bnext morning\b", r"\bnext day\b"
        ]
        if any(re.search(p, text) for p in time_skip_cues):
            return ZOOM_TIME_SKIP

        # Montage cues
        montage_cues = [
            r"\bmontage\b", r"\btraining montage\b",
            r"\bover the next (?:few|several) (?:days|weeks|months)\b",
            r"\bover the coming (?:days|weeks|months)\b",
            r"\bspend the next (?:few|several) (?:days|weeks|months)\b"
        ]
        if any(re.search(p, text) for p in montage_cues):
            return ZOOM_MONTAGE

        # Summary cues
        summary_cues = [
            r"\bsummarize\b", r"\bshort summary\b", r"\bquick summary\b",
            r"\bbriefly\b", r"\bin short\b", r"\bgloss over\b"
        ]
        if any(re.search(p, text) for p in summary_cues):
            return ZOOM_SHORT_SUMMARY

        # Combat / Conflict / Conversation cues default to detailed_scene
        conflict_cues = [r"\b(attack|strike|fight|shoot|slash|parry|dodge|block|cast|flee|ambush|confront|defend|stab|battle|grapple|duel)\b"]
        if any(re.search(p, text) for p in conflict_cues):
            return ZOOM_DETAILED_SCENE

        conv_cues = [r"\b(talk|speak|ask|tell|discuss|confer|negotiate|interrogate|question|whisper|reply|say|inquire|persuade|interview|argue|plead)\b"]
        if any(re.search(p, text) for p in conv_cues):
            return ZOOM_DETAILED_SCENE

        # Routine tasks
        routine_cues = [r"\b(train|practice|drill|exercise|workout|conditioning|sparring|meditate|cultivate)\b"]
        if any(re.search(p, text) for p in routine_cues):
            if any(term in text for term in ["days", "weeks", "months", "daily"]):
                return ZOOM_MONTAGE
            return ZOOM_SHORT_SUMMARY

        travel_cues = [r"\b(travel|journey|embark|transit|voyage|trek|march|commute|sail|fly|hike|walk to|ride to|head to)\b"]
        if any(re.search(p, text) for p in travel_cues):
            if any(term in text for term in ["days", "weeks", "months", "miles"]):
                return ZOOM_MONTAGE
            return ZOOM_SHORT_SUMMARY

        downtime_cues = [r"\b(rest|sleep|wait|pass time|downtime|work the shift|do chores|eat dinner|meals)\b"]
        if any(re.search(p, text) for p in downtime_cues):
            return ZOOM_SHORT_SUMMARY

        return ZOOM_DETAILED_SCENE

    @classmethod
    def recommend_intensity(cls, action_text: str, pacing_state: Optional[Dict[str, Any]] = None) -> int:
        """Recommends narrative intensity (1-5) from action keywords."""
        text = (action_text or "").lower()
        curr_intensity = int((pacing_state or {}).get("narrative_intensity", 1))

        high_stakes = ["ambush", "explosion", "assassination", "life or death", "mortal danger", "catastrophe", "critical failure", "boss fight", "last stand"]
        if any(w in text for w in high_stakes):
            return min(5, curr_intensity + 2)

        active_combat = ["attack", "fight", "shoot", "flee", "strike", "battle", "pursue", "clash"]
        if any(w in text for w in active_combat):
            return max(3, min(4, curr_intensity + 1))

        tension_cues = ["interrogate", "stealth", "sneak", "infiltrate", "threaten", "confront", "alarm"]
        if any(w in text for w in tension_cues):
            return 2 if curr_intensity <= 2 else 3

        routine_cues = ["train", "practice", "travel", "walk", "eat", "rest", "sleep", "study", "read", "downtime", "chores", "wait", "confer", "talk", "discuss"]
        if any(w in text for w in routine_cues):
            return 1 if curr_intensity <= 1 else 2

        return max(1, min(2, curr_intensity))

    @classmethod
    def advance_timeline_stamp(cls, old_stamp: str, start_min: int, end_min: int, delta_min: int) -> str:
        """Advances diegetic timestamp string deterministically."""
        if not old_stamp:
            day = 1 + (end_min // 1440)
            hh = (end_min % 1440) // 60
            mm = end_min % 60
            return f"Day {day}, {hh:02d}:{mm:02d}"

        m_day = re.search(r'Day\s+(\d+),\s*(\d{1,2}):(\d{2})', old_stamp, re.IGNORECASE)
        if m_day:
            day_num = int(m_day.group(1))
            hour = int(m_day.group(2))
            minute = int(m_day.group(3))
            base_minutes = (day_num - 1) * 1440 + hour * 60 + minute
            new_total = base_minutes + delta_min
            new_day = 1 + (new_total // 1440)
            new_hh = (new_total % 1440) // 60
            new_mm = new_total % 60
            return f"Day {new_day}, {new_hh:02d}:{new_mm:02d}"

        m_clock = re.search(r'^(\d{1,2}):(\d{2})(.*)$', old_stamp)
        if m_clock:
            hour = int(m_clock.group(1))
            minute = int(m_clock.group(2))
            suffix = m_clock.group(3)
            total_clock_min = hour * 60 + minute + delta_min
            new_hh = (total_clock_min % 1440) // 60
            new_mm = total_clock_min % 60
            days_passed = total_clock_min // 1440
            if days_passed > 0 and "Day" not in suffix:
                return f"Day {1 + days_passed}, {new_hh:02d}:{new_mm:02d}{suffix}"
            return f"{new_hh:02d}:{new_mm:02d}{suffix}"

        day = 1 + (end_min // 1440)
        hh = (end_min % 1440) // 60
        mm = end_min % 60
        return f"Day {day}, {hh:02d}:{mm:02d}"

    @classmethod
    def _match_rule(cls, rules: List[Dict[str, Any]], choice_index: Optional[int], action_text: str) -> Optional[Dict[str, Any]]:
        for r in rules:
            m = r.get("match", {})
            if "choice_index" in m and choice_index is not None:
                if m["choice_index"] == choice_index:
                    return r
            if "choice_text" in m and m["choice_text"]:
                if cls._matches_choice_text(action_text, m["choice_text"]):
                    return r
            if "action_regex" in m and m["action_regex"]:
                if re.search(m["action_regex"], action_text, re.IGNORECASE):
                    return r
        return None
