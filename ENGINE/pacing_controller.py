#!/usr/bin/env python3
"""
Adaptive Narrative Focus Controller & Event Clocks
=================================================
Provides persistent pacing control, narrative camera zoom management,
transition validation gates, and deterministic in-game time arithmetic
with event clocks for the Antigravity CYOA Engine.

Adheres strictly to CORE-002 (Turn, Pacing & Consequence Architecture)
and CORE-003 (GM Anti-Degradation Guards & Narrative Philosophy).
"""

import re
import copy
from typing import Dict, Any, List, Tuple, Optional

# Supported Zoom Levels
ZOOM_DETAILED_SCENE = "detailed_scene"
ZOOM_SHORT_SUMMARY = "short_summary"
ZOOM_MONTAGE = "montage"
ZOOM_TIME_SKIP = "time_skip"
VALID_ZOOM_LEVELS = [
    ZOOM_DETAILED_SCENE,
    ZOOM_SHORT_SUMMARY,
    ZOOM_MONTAGE,
    ZOOM_TIME_SKIP,
]

# Supported Pacing Profiles
PROFILE_SLOW = "slow"
PROFILE_BALANCED = "balanced"
PROFILE_FAST = "fast"
VALID_PACING_PROFILES = [PROFILE_SLOW, PROFILE_BALANCED, PROFILE_FAST]

# Scene Types
SCENE_CONVERSATION = "conversation"
SCENE_CONFLICT = "conflict"
SCENE_EXPLORATION = "exploration"
SCENE_DOWNTIME = "downtime"
SCENE_TRAVEL = "travel"
SCENE_ROUTINE = "routine"
VALID_SCENE_TYPES = [
    SCENE_CONVERSATION,
    SCENE_CONFLICT,
    SCENE_EXPLORATION,
    SCENE_DOWNTIME,
    SCENE_TRAVEL,
    SCENE_ROUTINE,
]


class PacingController:
    """
    Adaptive Focus Controller managing turn camera zoom, narrative intensity,
    explicit time tracking, and event clock triggers.
    """

    @staticmethod
    def create_default_pacing(
        scene_type: str = SCENE_EXPLORATION,
        scene_objective: str = "",
        narrative_intensity: int = 1,
        zoom_level: str = ZOOM_DETAILED_SCENE,
        elapsed_time_minutes: int = 0,
        timeline_stamp: str = "Day 1, 08:00",
        active_conflicts: Optional[List[str]] = None,
        unresolved_intentions: Optional[List[str]] = None,
        current_location: str = "Starting Area",
        pending_decisions: Optional[List[str]] = None,
        pacing_profile: str = PROFILE_BALANCED,
        scheduled_events: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new pacing_state dictionary compliant with turn_state.schema.json.
        """
        return {
            "scene_type": scene_type,
            "scene_objective": scene_objective,
            "narrative_intensity": max(1, min(5, narrative_intensity)),
            "zoom_level": zoom_level if zoom_level in VALID_ZOOM_LEVELS else ZOOM_DETAILED_SCENE,
            "elapsed_time_minutes": max(0, elapsed_time_minutes),
            "timeline_stamp": timeline_stamp,
            "active_conflicts": list(active_conflicts or []),
            "unresolved_intentions": list(unresolved_intentions or []),
            "current_location": current_location,
            "pending_decisions": list(pending_decisions or []),
            "pacing_profile": pacing_profile if pacing_profile in VALID_PACING_PROFILES else PROFILE_BALANCED,
            "scheduled_events": list(scheduled_events or []),
        }

    def validate_transition(
        self,
        current_pacing: Optional[Dict[str, Any]],
        proposed_action: str = "",
        proposed_zoom: Optional[str] = None,
        proposed_time_skip_minutes: int = 0,
        proposed_intensity: Optional[int] = None,
        proposed_location: Optional[str] = None,
        causal_justification: bool = False,
        explicit_permission: bool = False,
        **kwargs: Any,
    ) -> Tuple[bool, str]:
        """
        Validates proposed narrative transitions against anti-degradation gates.
        Returns (allowed: bool, reason: str).

        GATES:
        1. Zoom level validity: Proposed zoom must be in VALID_ZOOM_LEVELS if supplied.
        2. Unresolved Intentions: If unresolved_intentions exist in the current scene,
           rejects time skips (> 0 minutes or zoom_level == 'time_skip') without
           explicit justification or permission.
        3. Unearned Location Jumps: Rejects instantaneous relocation jumps to different
           locations when active conflicts or unresolved intentions are present, or when
           no travel action/justification is provided.
        4. Dramatic Escalation: Prevents jumping narrative intensity by more than 2 steps
           (e.g., from 1 to 4 or 2 to 5) without causal justification.
        5. Premature Resolution: Prevents skipping active conflicts without earned action steps.
        """
        pacing = current_pacing or {}
        action_text = (proposed_action or "").strip()
        action_lower = action_text.lower()

        # Handle alias kwargs
        has_causal_justification = (
            causal_justification
            or kwargs.get("has_causal_justification", False)
            or self._detect_causal_justification(action_lower)
        )
        has_permission = (
            explicit_permission
            or kwargs.get("allow_unresolved", False)
            or kwargs.get("permission", False)
            or self._detect_explicit_permission(action_lower)
        )

        # 1. Zoom level check
        if proposed_zoom is not None and proposed_zoom not in VALID_ZOOM_LEVELS:
            return False, f"Invalid zoom level '{proposed_zoom}'. Must be one of: {VALID_ZOOM_LEVELS}."

        if proposed_time_skip_minutes < 0:
            return False, f"Time skip cannot be negative ({proposed_time_skip_minutes} minutes)."

        is_time_jump = (
            proposed_zoom == ZOOM_TIME_SKIP
            or proposed_time_skip_minutes > 0
            or self._detect_time_jump_intent(action_lower)
        )

        # 2. Gate: Unresolved Intentions
        unresolved = pacing.get("unresolved_intentions", [])
        if unresolved and len(unresolved) > 0 and is_time_jump:
            if not has_permission and not has_causal_justification:
                intentions_str = ", ".join(f"'{i}'" for i in unresolved)
                return (
                    False,
                    f"Transition rejected: Cannot advance time or skip scene ({proposed_time_skip_minutes} min, "
                    f"zoom='{proposed_zoom}') while unresolved intentions exist: [{intentions_str}] "
                    f"without explicit justification or permission.",
                )

        # 3. Gate: Unearned Location Jumps
        curr_loc = pacing.get("current_location", "")
        if proposed_location and curr_loc and proposed_location.strip() != curr_loc.strip():
            # If unresolved intentions or active conflicts exist in current location
            conflicts = pacing.get("active_conflicts", [])
            if (unresolved or conflicts) and not (has_permission or has_causal_justification):
                return (
                    False,
                    f"Unearned location jump to '{proposed_location}' rejected: active conflicts or "
                    f"unresolved intentions remain in current location '{curr_loc}'.",
                )

            # Check if action provides travel context or movement rationale
            travel_terms = [
                "travel", "journey", "embark", "walk", "ride", "fly", "march", "head to",
                "go to", "transit", "voyage", "trek", "escape", "flee", "teleport",
                "portal", "arrive", "take the", "board", "run to", "move to"
            ]
            has_travel_action = any(term in action_lower for term in travel_terms)
            if not has_travel_action and not has_permission and not has_causal_justification:
                return (
                    False,
                    f"Unearned location jump to '{proposed_location}' rejected: action does not contain "
                    f"travel or transit justification from '{curr_loc}'.",
                )

        # 4. Gate: Dramatic Escalation (> 2 steps intensity increase without causal justification)
        current_intensity = pacing.get("narrative_intensity", 1)
        target_intensity = proposed_intensity if proposed_intensity is not None else kwargs.get("intensity")
        if target_intensity is not None:
            intensity_delta = target_intensity - current_intensity
            if intensity_delta > 2 and not has_causal_justification:
                return (
                    False,
                    f"Dramatic escalation rejected: intensity increase of {intensity_delta} steps "
                    f"(from {current_intensity} to {target_intensity}) exceeds threshold of 2 without causal justification.",
                )

        # 5. Gate: Premature Resolution
        active_conflicts = pacing.get("active_conflicts", [])
        if active_conflicts and len(active_conflicts) > 0:
            premature_phrases = [
                "instantly defeat", "i win", "skip the fight", "skip the battle",
                "they all drop dead", "victory is mine automatically", "kill everyone instantly"
            ]
            if any(phrase in action_lower for phrase in premature_phrases):
                return (
                    False,
                    "Premature resolution rejected: active conflicts cannot be bypassed without earned tactical steps.",
                )

        return True, "Transition approved."

    def evaluate_focus(
        self,
        action_text: str,
        current_pacing: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Determines the appropriate narrative zoom level based on player intent and activity.

        Rules:
        - Player explicit requests override default behavior:
          - "zoom in", "elaborate", "in detail" -> detailed_scene
          - "skip to next morning", "time skip", "fast forward" -> time_skip
          - "montage", "over the next few weeks" -> montage
          - "summarize", "quick summary", "briefly" -> short_summary
        - Detailed scenes for:
          - Conversations, discoveries/investigations, combat/conflicts, meaningful decisions.
        - Summaries or montages for:
          - Routine training, travel, work, downtime unless the player explicitly requests focus.
        """
        action_lower = (action_text or "").lower().strip()
        pacing = current_pacing or {}

        # 1. Explicit player requests for zoom / detail
        # Greater detail / zoom in
        detailed_scene_cues = [
            r"\bzoom in\b",
            r"\belaborate\b",
            r"\bin detail\b",
            r"\bin full detail\b",
            r"\bfocus on\b",
            r"\bstep by step\b",
            r"\bexamine closely\b",
            r"\blook closely\b",
            r"\btake my time\b",
            r"\bslow down\b",
            r"\bplay out\b",
            r"\bdetailed scene\b",
        ]
        if any(re.search(pat, action_lower) for pat in detailed_scene_cues):
            return ZOOM_DETAILED_SCENE

        # Explicit time skip
        time_skip_cues = [
            r"\bskip to\b",
            r"\btime skip\b",
            r"\bskip ahead\b",
            r"\bfast forward\b",
            r"\bjump ahead\b",
            r"\bwait until morning\b",
            r"\bsleep until\b",
            r"\buntil tomorrow\b",
            r"\bnext morning\b",
            r"\bnext day\b",
            r"\badvance to the next\b",
        ]
        if any(re.search(pat, action_lower) for pat in time_skip_cues):
            return ZOOM_TIME_SKIP

        # Explicit montage
        montage_cues = [
            r"\bmontage\b",
            r"\btraining montage\b",
            r"\bover the next (?:few|several) (?:days|weeks|months)\b",
            r"\bover the coming (?:days|weeks|months)\b",
            r"\bover the course of (?:several|the next)\b",
            r"\bspend the next (?:few|several) (?:days|weeks|months)\b",
        ]
        if any(re.search(pat, action_lower) for pat in montage_cues):
            return ZOOM_MONTAGE

        # Explicit summary
        summary_cues = [
            r"\bsummarize\b",
            r"\bshort summary\b",
            r"\bquick summary\b",
            r"\bbriefly\b",
            r"\bin short\b",
            r"\bgloss over\b",
        ]
        if any(re.search(pat, action_lower) for pat in summary_cues):
            return ZOOM_SHORT_SUMMARY

        # 2. Activity classification when no explicit directive was given
        # A. Conflict, combat, confrontation
        conflict_cues = [
            r"\b(attack|strike|fight|shoot|slash|parry|dodge|block|cast|flee|ambush|confront|defend|stab|battle|grapple|duel)\b"
        ]
        if any(re.search(pat, action_lower) for pat in conflict_cues):
            return ZOOM_DETAILED_SCENE

        # B. Conversation, social interaction, interrogation
        conversation_cues = [
            r"\b(talk|speak|ask|tell|discuss|confer|negotiate|interrogate|question|whisper|reply|say|inquire|persuade|interview|argue|plead)\b"
        ]
        if any(re.search(pat, action_lower) for pat in conversation_cues):
            return ZOOM_DETAILED_SCENE

        # C. Active exploration, discovery, puzzle solving
        discovery_cues = [
            r"\b(investigate|inspect|search|examine|analyze|look around|read the|study|uncover|decode|pick the lock|disarm)\b"
        ]
        if any(re.search(pat, action_lower) for pat in discovery_cues):
            return ZOOM_DETAILED_SCENE

        # D. Meaningful decisions or commitments
        decision_cues = [
            r"\b(choose|decide|sign|accept the contract|reject the offer|swear|betray)\b"
        ]
        if any(re.search(pat, action_lower) for pat in decision_cues):
            return ZOOM_DETAILED_SCENE

        # E. Existing active conflicts or high narrative intensity defaults to detailed scene
        if len(pacing.get("active_conflicts", [])) > 0 or pacing.get("narrative_intensity", 1) >= 3:
            return ZOOM_DETAILED_SCENE
        if pacing.get("scene_type") in [SCENE_CONFLICT, SCENE_CONVERSATION]:
            return ZOOM_DETAILED_SCENE

        # F. Routine tasks: training, travel, work, downtime default to summary / montage
        # Routine training
        routine_training_cues = [
            r"\b(train|practice|drill|exercise|workout|conditioning|sparring|meditate|cultivate|katas)\b"
        ]
        if any(re.search(pat, action_lower) for pat in routine_training_cues):
            # If multi-day or extended routine -> montage
            if any(term in action_lower for term in ["days", "weeks", "months", "daily", "routine", "cycle"]):
                return ZOOM_MONTAGE
            return ZOOM_SHORT_SUMMARY

        # Routine travel
        travel_cues = [
            r"\b(travel|journey|embark|transit|voyage|trek|march|commute|sail|fly|hike|walk to|ride to|head to|head toward|head towards|make my way)\b"
        ]
        if any(re.search(pat, action_lower) for pat in travel_cues):
            if any(term in action_lower for term in ["days", "weeks", "months", "miles", "long journey", "march across", "expedition"]):
                return ZOOM_MONTAGE
            return ZOOM_SHORT_SUMMARY

        # Downtime / work / chores
        downtime_cues = [
            r"\b(rest|sleep|wait|pass time|downtime|work the shift|do chores|eat dinner|meals|daily routine|craft|forge|repair)\b"
        ]
        if any(re.search(pat, action_lower) for pat in downtime_cues):
            if any(term in action_lower for term in ["days", "weeks", "extended", "prolonged"]):
                return ZOOM_MONTAGE
            return ZOOM_SHORT_SUMMARY

        # If scene_type in current pacing is already routine, downtime, or travel
        current_scene_type = pacing.get("scene_type")
        if current_scene_type == SCENE_ROUTINE:
            return ZOOM_MONTAGE
        if current_scene_type in [SCENE_TRAVEL, SCENE_DOWNTIME]:
            return ZOOM_SHORT_SUMMARY

        # Standard fallback for active interactive play
        return ZOOM_DETAILED_SCENE

    def recommend_intensity(
        self,
        action_text: str,
        current_pacing: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Recommends appropriate narrative intensity (1-5) based on activity and current state.
        Ensures ordinary scenes maintain low narrative intensity (1-2) without artificial escalation.
        """
        action_lower = (action_text or "").lower()
        pacing = current_pacing or {}
        curr_intensity = pacing.get("narrative_intensity", 1)

        # High stakes / lethal danger / climax (Intensity 4-5)
        high_stakes = [
            "ambush", "explosion", "assassination", "life or death", "mortal danger",
            "catastrophe", "critical failure", "boss fight", "last stand"
        ]
        if any(w in action_lower for w in high_stakes):
            return min(5, curr_intensity + 2)

        # Active combat / pursuit (Intensity 3-4)
        active_combat = ["attack", "fight", "shoot", "flee", "strike", "battle", "pursue", "clash"]
        if any(w in action_lower for w in active_combat):
            return max(3, min(4, curr_intensity + 1))

        # Moderate tension / tense interrogation (Intensity 2-3)
        tension_cues = ["interrogate", "stealth", "sneak", "infiltrate", "threaten", "confront", "alarm"]
        if any(w in action_lower for w in tension_cues):
            return 2 if curr_intensity <= 2 else 3

        # Routine tasks, quiet meals, travel, downtime, study -> strictly 1-2
        routine_cues = [
            "train", "practice", "travel", "walk", "eat", "rest", "sleep",
            "study", "read", "downtime", "chores", "wait", "confer", "talk", "discuss"
        ]
        if any(w in action_lower for w in routine_cues) or pacing.get("scene_type") in [
            SCENE_ROUTINE, SCENE_DOWNTIME, SCENE_TRAVEL, SCENE_EXPLORATION
        ]:
            return 1 if curr_intensity <= 1 else 2

        # Default ordinary baseline
        return max(1, min(2, curr_intensity))

    def validate_progression_pacing(
        self,
        zoom_level: str,
        scene_type: str,
        delta: int,
        is_milestone: bool = False,
        is_cycle_end: bool = False,
    ) -> Tuple[bool, str]:
        """
        Enforces the campaign-agnostic Zero Micro-Scene Rule:
        - Routine conversation, transit, meals, shopping, or low-intensity scene tasks yield Delta: 0 progression advancement.
        - Advancement deltas (> 0) require either:
          a) montage zoom level,
          b) completed cycle/evening wind-down (is_cycle_end=True), or
          c) structured milestone / tournament / trial bout (is_milestone=True).
        """
        if delta == 0:
            return True, "Zero micro-scene progression delta approved."

        if delta < 0:
            return True, "Resource/progression expenditure or strain penalty approved."

        # delta > 0: check if pacing justifies progression advancement
        if is_milestone or is_cycle_end or zoom_level in [ZOOM_MONTAGE, ZOOM_TIME_SKIP]:
            return True, "Progression advancement approved for macro pacing or milestone."

        if scene_type in [SCENE_CONVERSATION, SCENE_TRAVEL, SCENE_DOWNTIME, SCENE_ROUTINE]:
            return False, (
                f"Progression pacing violation: Scene type '{scene_type}' under '{zoom_level}' zoom "
                f"must award Delta: 0 advancement (Zero Micro-Scene Rule). "
                f"Progression advancement is reserved for completed routine cycles, combat/sparring trials, or major milestones."
            )

        return True, "Progression advancement approved."

    def recommend_progression_envelope(
        self,
        zoom_level: str,
        scene_type: str,
        is_milestone: bool = False,
        is_cycle_end: bool = False,
    ) -> Dict[str, Any]:
        """
        Provides campaign-agnostic progression guidance for the current pacing context.
        """
        if is_milestone:
            return {
                "allowed": True,
                "reason": "Milestone / tournament / major breakthrough",
                "recommended_delta_type": "milestone_package",
            }
        if is_cycle_end:
            return {
                "allowed": True,
                "reason": "Daily/weekly cycle wind-down closure",
                "recommended_delta_type": "cycle_routine",
            }
        if zoom_level in [ZOOM_MONTAGE, ZOOM_TIME_SKIP]:
            return {
                "allowed": True,
                "reason": "Extended time compression / montage",
                "recommended_delta_type": "montage_macro",
            }
        if scene_type in [SCENE_CONVERSATION, SCENE_TRAVEL, SCENE_DOWNTIME, SCENE_ROUTINE]:
            return {
                "allowed": False,
                "reason": "Routine scene task: strictly Delta: 0 (Zero Micro-Scene Rule)",
                "recommended_delta_type": "zero_delta",
            }
        return {
            "allowed": True,
            "reason": "Active combat / challenge scene phase",
            "recommended_delta_type": "phase_award",
        }

    def advance_time(
        self,
        current_pacing: Dict[str, Any],
        delta_minutes: int,
        world_events: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Performs explicit in-game time arithmetic, updates elapsed minutes and timestamps,
        and checks for and triggers any scheduled world events crossed.

        Returns (updated_pacing_state, triggered_simulation_events).
        """
        if delta_minutes < 0:
            raise ValueError(f"delta_minutes cannot be negative: {delta_minutes}")

        updated = copy.deepcopy(current_pacing)
        start_time = updated.get("elapsed_time_minutes", 0)
        end_time = start_time + delta_minutes
        updated["elapsed_time_minutes"] = end_time

        # Update timeline_stamp
        old_stamp = updated.get("timeline_stamp", "")
        updated["timeline_stamp"] = self._advance_timeline_stamp(old_stamp, start_time, end_time, delta_minutes)

        # Merge any external world_events into scheduled_events if not already present
        scheduled = updated.setdefault("scheduled_events", [])
        existing_ids = {evt["id"] for evt in scheduled if "id" in evt}
        if world_events:
            for wevt in world_events:
                if wevt.get("id") not in existing_ids:
                    scheduled.append(copy.deepcopy(wevt))
                    existing_ids.add(wevt.get("id"))

        # Check for crossed event clocks
        triggered_events = []
        for evt in scheduled:
            trigger_time = evt.get("trigger_time_minutes", 0)
            fired = evt.get("fired", False)

            # Trigger condition: not already fired and crossed during this time step
            if not fired:
                if start_time < trigger_time <= end_time or (start_time == 0 and trigger_time == 0):
                    evt["fired"] = True
                    triggered_events.append(copy.deepcopy(evt))

        return updated, triggered_events

    def add_scheduled_event(
        self,
        pacing_state: Dict[str, Any],
        event_id: str,
        trigger_time_minutes: int,
        description: str,
    ) -> Dict[str, Any]:
        """
        Registers a new scheduled event clock into pacing state.
        """
        updated = copy.deepcopy(pacing_state)
        events = updated.setdefault("scheduled_events", [])
        # Overwrite if exists, else append
        for evt in events:
            if evt.get("id") == event_id:
                evt["trigger_time_minutes"] = trigger_time_minutes
                evt["description"] = description
                evt["fired"] = False
                return updated

        events.append({
            "id": event_id,
            "trigger_time_minutes": trigger_time_minutes,
            "description": description,
            "fired": False,
        })
        return updated

    # Internal helper methods
    @staticmethod
    def _detect_causal_justification(action_lower: str) -> bool:
        cues = [
            "ambush", "explosion", "sudden attack", "betrayal", "catastrophe",
            "emergency", "critical failure", "life or death", "causal justification",
            "alarm sounds", "ship breach", "building collapses"
        ]
        return any(cue in action_lower for cue in cues)

    @staticmethod
    def _detect_explicit_permission(action_lower: str) -> bool:
        cues = [
            "with permission", "explicit permission", "abandoning intention",
            "abandon intention", "postpone intention", "defer intention",
            "skip intention", "permission granted", "authorized skip"
        ]
        return any(cue in action_lower for cue in cues)

    @staticmethod
    def _detect_time_jump_intent(action_lower: str) -> bool:
        cues = [
            "skip to", "time skip", "skip ahead", "fast forward",
            "sleep until tomorrow", "wait until morning", "jump to next"
        ]
        return any(cue in action_lower for cue in cues)

    @staticmethod
    def _advance_timeline_stamp(old_stamp: str, start_min: int, end_min: int, delta_min: int) -> str:
        """
        Advances diegetic calendar / clock timestamp string.
        Supports standard formats:
        - "Day X, HH:MM"
        - "HH:MM Local Cycle"
        - Fallbacks gracefully to appending minutes or generating "Day X, HH:MM".
        """
        if not old_stamp:
            day = 1 + (end_min // 1440)
            hh = (end_min % 1440) // 60
            mm = end_min % 60
            return f"Day {day}, {hh:02d}:{mm:02d}"

        # Match "Day X, HH:MM" pattern
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

        # Match "HH:MM Local Cycle" or similar suffix pattern
        m_clock = re.search(r'(\d{1,2}):(\d{2})(.*)', old_stamp)
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

        # Fallback: Day + minutes formatting
        day = 1 + (end_min // 1440)
        hh = (end_min % 1440) // 60
        mm = end_min % 60
        return f"{old_stamp} (+{delta_min}m -> Day {day}, {hh:02d}:{mm:02d})"
