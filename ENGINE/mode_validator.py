#!/usr/bin/env python3
"""
Deterministic Mode Validator & Action Parser
============================================
Provides deterministic operational mode separation and action validation
for the Antigravity CYOA Engine.

Supported Modes:
- "classic_cyoa": Strict choice selection. Deterministically validates action
  input against offered choices extracted from the latest active turn file in TURNS/ACTIVE/
  (or fallback status/upcoming hooks). Rejects arbitrary freeform prose, compound/chained
  actions (e.g. "1 and then search", "1, 2"), and out-of-range option indices.
- "freeform_simulation": Emergent simulation mode. Allows freeform prose actions and
  compound actions (action chaining), validating that input is non-empty and well-formed.
"""

import os
import re
import json
import glob

DEFAULT_OPERATIONAL_MODE = "classic_cyoa"
VALID_OPERATIONAL_MODES = ["classic_cyoa", "freeform_simulation"]

DEFAULT_FALLBACK_CHOICES = [
    {
        "index": 1,
        "text": "Press forward along your primary path.",
        "raw": "1. Press forward along your primary path."
    },
    {
        "index": 2,
        "text": "Inspect your immediate environment for hidden clues or resources.",
        "raw": "2. Inspect your immediate environment for hidden clues or resources."
    },
    {
        "index": 3,
        "text": "Confer with your companions to consolidate strategy.",
        "raw": "3. Confer with your companions to consolidate strategy."
    },
    {
        "index": 4,
        "text": "Rest and recover your somatic vitals before proceeding.",
        "raw": "4. Rest and recover your somatic vitals before proceeding."
    }
]

def _get_root_dir() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, ".."))

def get_campaign_mode(campaign_id: str, root_dir: str = None) -> str:
    """
    Reads the operational mode configured for a campaign in campaign_config.json.
    Returns 'classic_cyoa' or 'freeform_simulation' (defaults to 'classic_cyoa').
    """
    if not campaign_id:
        return DEFAULT_OPERATIONAL_MODE
    root = root_dir or _get_root_dir()
    config_path = os.path.join(root, "CAMPAIGNS", campaign_id, "campaign_config.json")
    if not os.path.isfile(config_path):
        return DEFAULT_OPERATIONAL_MODE
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            mode = data.get("operational_mode")
            if mode in VALID_OPERATIONAL_MODES:
                return mode
    except Exception:
        pass
    return DEFAULT_OPERATIONAL_MODE

def extract_options_from_text(text: str) -> list[dict]:
    """
    Extracts numbered choice options from narrative text.
    Looks for [OPTIONS & TYPABLE REFERENCE] or [OPTIONS] blocks,
    and falls back to finding numbered choice lines.
    """
    if not text:
        return []

    # Check for [OPTIONS...] section block
    section_match = re.search(
        r'\[OPTIONS(?:\s*&\s*TYPABLE\s*REFERENCE)?\](.*?)(?=\n\s*\[SYS:|\n\s*---|\Z)',
        text,
        re.DOTALL | re.IGNORECASE
    )
    block = section_match.group(1) if section_match else text

    choices = []
    choice_pattern = re.compile(r'^\s*(\d+)[\.\)]\s+(.*?)\s*$', re.MULTILINE)
    for m in choice_pattern.finditer(block):
        idx = int(m.group(1))
        desc = m.group(2).strip()
        choices.append({
            "index": idx,
            "text": desc,
            "raw": m.group(0).strip()
        })
    return choices

def _get_turn_number(filename: str) -> int:
    match = re.search(r'turn_(\d+)', filename)
    return int(match.group(1)) if match else -1

def extract_offered_choices(campaign_id: str = None, root_dir: str = None) -> list[dict]:
    """
    Extracts valid offered choices for a campaign:
    1. Checks the latest active turn file in TURNS/ACTIVE/
    2. Fallback: Checks GAMEPLAY/upcoming_hooks.md
    3. Fallback: Default standard choices
    """
    root = root_dir or _get_root_dir()
    if campaign_id:
        campaign_dir = os.path.join(root, "CAMPAIGNS", campaign_id)
        active_dir = os.path.join(campaign_dir, "TURNS", "ACTIVE")
        if os.path.isdir(active_dir):
            turn_files = sorted(glob.glob(os.path.join(active_dir, "turn_*.md")), key=_get_turn_number)
            if turn_files:
                latest_file = turn_files[-1]
                try:
                    with open(latest_file, "r", encoding="utf-8") as f:
                        turn_text = f.read()
                    choices = extract_options_from_text(turn_text)
                    if choices:
                        return choices
                except Exception:
                    pass

        # Check upcoming hooks fallback
        hooks_file = os.path.join(campaign_dir, "GAMEPLAY", "upcoming_hooks.md")
        if os.path.isfile(hooks_file):
            try:
                with open(hooks_file, "r", encoding="utf-8") as f:
                    hooks_text = f.read()
                choices = extract_options_from_text(hooks_text)
                if choices:
                    return choices
            except Exception:
                pass

    return list(DEFAULT_FALLBACK_CHOICES)

def _normalize_text(text: str) -> str:
    """Removes cost tags, punctuation, and extra whitespace for fuzzy comparison."""
    if not text:
        return ""
    # Strip cost / bracketed tags like [Cost: ...]
    no_brackets = re.sub(r'\[.*?\]', '', text)
    # Strip punctuation and lowercase
    cleaned = re.sub(r'[^\w\s]', ' ', no_brackets.lower())
    return ' '.join(cleaned.split())

def matches_choice_text(candidate: str, target: str) -> bool:
    """Determines whether candidate input matches the target option text."""
    norm_cand = _normalize_text(candidate)
    norm_target = _normalize_text(target)
    if not norm_cand or not norm_target:
        return False
    if norm_cand == norm_target:
        return True

    # Target often contains title and description, e.g. "Accept Contract Alpha: Infiltrate..."
    # Check title portion before colon or dash
    split_parts = re.split(r'[:\-–—]', target, maxsplit=1)
    if len(split_parts) > 1:
        norm_title = _normalize_text(split_parts[0])
        if norm_cand == norm_title:
            return True

    # If candidate is a prefix of target with sufficient length (at least 15 chars or entire title)
    if len(norm_cand) >= 15 and norm_target.startswith(norm_cand):
        return True

    return False

def is_compound_action(raw_action: str, extra_text: str = None) -> bool:
    """
    Detects whether an action represents a compound / combined action
    (e.g. multiple options chained together or action followed by another verb/command).
    """
    text = raw_action.strip()
    
    # 1. Multiple numbered options: e.g. "1, 2", "1 and 2", "1 & 2", "1,2", "Option 1 and Option 2"
    multi_option_pattern = re.compile(
        r'^(?:option\s+|choice\s+)?(\d+)\s*(?:,|&|\band\b|\+|(?:and\s+)?then)\s*(?:option\s+|choice\s+)?(\d+)',
        re.IGNORECASE
    )
    if multi_option_pattern.search(text):
        return True

    # 2. Option followed by chaining conjunction and action words:
    # e.g. "1 and then search", "1 then search", "1, search", "1; search", "1 and search"
    chained_num_pattern = re.compile(
        r'^(?:(?:option|choice)\s+)?\d+\s*[\.\)]?\s*(?:and\s+then|then|and|&|,|;|followed\s+by|\+)\s+(.+)$',
        re.IGNORECASE
    )
    if chained_num_pattern.match(text):
        return True

    # 3. Explicit chaining phrases in prose: "and then", "followed by"
    if re.search(r'\b(?:and\s+then|then\s+also|followed\s+by)\b', text, re.IGNORECASE):
        return True

    # If extra_text was extracted after an option number (e.g. from "1. ..."):
    if extra_text:
        extra_stripped = extra_text.strip()
        if re.match(r'^(?:and\s+then|then|and|&|,|;|followed\s+by|\+)\b', extra_stripped, re.IGNORECASE):
            return True

    return False

def validate_action(
    action: str,
    mode: str = None,
    campaign_id: str = None,
    root_dir: str = None,
    offered_choices: list[dict] = None
) -> tuple[bool, str, dict]:
    """
    Deterministically validates player action against the operational mode.

    Parameters:
    - action: Raw action input from the player.
    - mode: "classic_cyoa" or "freeform_simulation" (if None, resolved from campaign_config).
    - campaign_id: ID of the active campaign.
    - root_dir: Workspace root directory.
    - offered_choices: Optional pre-extracted choices list; if None, extracted automatically.

    Returns:
    (is_valid: bool, error_msg: str, parsed_action: dict)
    """
    root = root_dir or _get_root_dir()

    if action is None or not str(action).strip():
        return False, "Action input cannot be empty.", {}

    clean_action = str(action).strip()

    # Resolve operational mode
    if not mode:
        mode = get_campaign_mode(campaign_id, root) if campaign_id else DEFAULT_OPERATIONAL_MODE
    if mode not in VALID_OPERATIONAL_MODES:
        mode = DEFAULT_OPERATIONAL_MODE

    # -------------------------------------------------------------
    # FREEFORM SIMULATION MODE
    # -------------------------------------------------------------
    if mode == "freeform_simulation":
        # Freeform mode accepts arbitrary prose and compound/chained actions
        return True, "", {
            "index": None,
            "text": clean_action,
            "raw_input": action,
            "mode": "freeform_simulation"
        }

    # -------------------------------------------------------------
    # CLASSIC CYOA MODE
    # -------------------------------------------------------------
    if offered_choices is None:
        offered_choices = extract_offered_choices(campaign_id, root)
    if not offered_choices:
        offered_choices = list(DEFAULT_FALLBACK_CHOICES)

    choice_map = {c["index"]: c for c in offered_choices}
    min_idx = min(choice_map.keys())
    max_idx = max(choice_map.keys())

    # 1. Early rejection: compound multi-option selection (e.g. "1, 2", "1 and 2", "Option 1 and Option 2")
    multi_opt_match = re.match(
        r'^(?:option\s+|choice\s+)?(\d+)\s*(?:,|&|\band\b|\+|(?:and\s+)?then)\s*(?:option\s+|choice\s+)?(\d+)',
        clean_action,
        re.IGNORECASE
    )
    if multi_opt_match:
        return False, "Compound actions are not permitted in Classic CYOA mode. Please select a single offered option.", {}

    # 2. Pure single integer (e.g. "1", "2")
    m_int = re.fullmatch(r'(\d+)', clean_action)
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

    # 3. Option or Choice prefix (e.g. "Option 1", "choice 2", "Option 1.", "Option 1)")
    m_opt = re.fullmatch(r'(?:option|choice)\s+(\d+)[\.\)]?', clean_action, re.IGNORECASE)
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

    # 4. Number with dot or parenthesis only (e.g. "1.", "2)")
    m_dot = re.fullmatch(r'(\d+)[\.\)]', clean_action)
    if m_dot:
        idx = int(m_dot.group(1))
        if idx in choice_map:
            return True, "", {
                "index": idx,
                "text": choice_map[idx]["text"],
                "raw_input": action,
                "mode": "classic_cyoa"
            }
        return False, f"Option {idx} is out of range. Valid options are {min_idx} to {max_idx}.", {}

    # 5. Number followed by separator and text (e.g. "1. Accept Contract Alpha...", "Option 1: Accept...")
    m_numbered_text = re.match(
        r'^(?:(?:option|choice)\s+)?(\d+)[\.\)\:\-]?\s+(.*)$',
        clean_action,
        re.IGNORECASE
    )
    if m_numbered_text:
        idx = int(m_numbered_text.group(1))
        rest = m_numbered_text.group(2).strip()

        # Check if rest matches the text of option idx
        if idx in choice_map and matches_choice_text(rest, choice_map[idx]["text"]):
            return True, "", {
                "index": idx,
                "text": choice_map[idx]["text"],
                "raw_input": action,
                "mode": "classic_cyoa"
            }

        # Check if rest represents a compound action (e.g. "and then search", ", search")
        if is_compound_action(clean_action, rest):
            return False, "Compound actions are not permitted in Classic CYOA mode. Please select a single offered option.", {}

        if idx not in choice_map:
            return False, f"Option {idx} is out of range. Valid options are {min_idx} to {max_idx}.", {}

        return False, "Arbitrary freeform actions are not permitted in Classic CYOA mode. Please select one of the offered numbered options.", {}

    # 6. Check if input matches any choice text directly (without index number)
    for idx, choice in sorted(choice_map.items()):
        if matches_choice_text(clean_action, choice["text"]):
            return True, "", {
                "index": idx,
                "text": choice["text"],
                "raw_input": action,
                "mode": "classic_cyoa"
            }

    # 7. Check general compound action
    if is_compound_action(clean_action):
        return False, "Compound actions are not permitted in Classic CYOA mode. Please select a single offered option.", {}

    # 8. Check if out-of-range integer is present
    m_any_num = re.search(r'\b(\d+)\b', clean_action)
    if m_any_num:
        num = int(m_any_num.group(1))
        if num not in choice_map:
            return False, f"Option {num} is out of range. Valid options are {min_idx} to {max_idx}.", {}

    # Negative numbers e.g. "-1"
    if re.search(r'-\d+', clean_action):
        return False, f"Negative option is out of range. Valid options are {min_idx} to {max_idx}.", {}

    # 9. Freeform prose rejected
    return False, "Arbitrary freeform actions are not permitted in Classic CYOA mode. Please select one of the offered numbered options.", {}


class ModeValidator:
    """Class wrapper providing static access to mode validation and choice extraction."""
    validate_action = staticmethod(validate_action)
    get_campaign_mode = staticmethod(get_campaign_mode)
    is_compound_action = staticmethod(is_compound_action)
    extract_options_from_text = staticmethod(extract_options_from_text)
    extract_offered_choices = staticmethod(extract_offered_choices)
    matches_choice_text = staticmethod(matches_choice_text)
