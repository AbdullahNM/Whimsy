"""
Whimsy CYOA Engine — Inter-Narrator Coordination Channel
Governs autonomous communication between the Shadow Narrator (Background Architect)
and the Active GM (Diegetic Storyteller).

Enforces:
1. Maximum 5 messages from each agent role (10 messages total max).
2. Autonomous steering by the Shadow Narrator without human intervention.
3. Fixed-interval or event-triggered sync by the Active GM.
4. Clean Markdown serialization and JSON dual-persistence.
"""

import os
import re
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


DEFAULT_MAX_PER_SENDER = 5
CHANNEL_FILENAME_MD = "agent_channel.md"
CHANNEL_FILENAME_JSON = "agent_channel.json"


def normalize_sender(sender: str) -> str:
    s = sender.strip().upper()
    if "SHADOW" in s:
        return "SHADOW"
    if "ACTIVE" in s or "GM" in s:
        return "ACTIVE"
    return s


def prune_channel_messages(messages: List[Dict[str, Any]], max_per_sender: int = DEFAULT_MAX_PER_SENDER) -> List[Dict[str, Any]]:
    """
    Prunes messages so that at most `max_per_sender` messages exist for each sender role.
    Preserves the relative chronological order of retained messages.
    """
    shadow_msgs = []
    active_msgs = []
    other_msgs = []

    for idx, msg in enumerate(messages):
        sender = normalize_sender(msg.get("sender", ""))
        item = (idx, msg)
        if sender == "SHADOW":
            shadow_msgs.append(item)
        elif sender == "ACTIVE":
            active_msgs.append(item)
        else:
            other_msgs.append(item)

    # Keep only the last `max_per_sender` messages for each
    retained_shadow = shadow_msgs[-max_per_sender:] if len(shadow_msgs) > max_per_sender else shadow_msgs
    retained_active = active_msgs[-max_per_sender:] if len(active_msgs) > max_per_sender else active_msgs
    retained_other = other_msgs[-max_per_sender:] if len(other_msgs) > max_per_sender else other_msgs

    # Combine and sort back into original index order
    all_retained = retained_shadow + retained_active + retained_other
    all_retained.sort(key=lambda x: x[0])

    return [msg for _, msg in all_retained]


def parse_channel_markdown(markdown_text: str) -> List[Dict[str, Any]]:
    """
    Parses an agent_channel.md file into structured message dictionaries.
    """
    messages: List[Dict[str, Any]] = []
    # Pattern matching: ### [MSG-001] SHADOW -> ACTIVE | Turn 260 | 2026-11-09T00:15:00
    header_regex = re.compile(
        r"^###\s+\[(?P<id>[^\]]+)\]\s+(?P<sender>[A-Za-z_-]+)\s*(?:->\s*(?P<recipient>[A-Za-z_-]+))?(?:\s*\|\s*Turn\s*(?P<turn>\d+))?(?:\s*\|\s*(?P<timestamp>[^\n]+))?",
        re.MULTILINE
    )

    matches = list(header_regex.finditer(markdown_text))
    for i, match in enumerate(matches):
        msg_id = match.group("id").strip()
        sender = normalize_sender(match.group("sender"))
        recipient = normalize_sender(match.group("recipient") or ("ACTIVE" if sender == "SHADOW" else "SHADOW"))
        turn_str = match.group("turn")
        turn = int(turn_str) if turn_str else None
        timestamp = match.group("timestamp").strip() if match.group("timestamp") else ""

        # Content is between this header and the next header (or end of string)
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_text)
        raw_content = markdown_text[start_pos:end_pos].strip()
        cleaned_content = re.sub(r"\n+---+\s*$", "", raw_content).strip()
        cleaned_content = re.sub(r"^---+[\r\n]+", "", cleaned_content).strip()

        messages.append({
            "id": msg_id,
            "sender": sender,
            "recipient": recipient,
            "turn": turn,
            "timestamp": timestamp,
            "content": cleaned_content
        })

    return messages


def format_channel_markdown(messages: List[Dict[str, Any]], campaign_id: str = "") -> str:
    """
    Serializes a list of channel messages into standard Whimsy agent_channel.md Markdown.
    """
    lines = [
        "# AGENT CHANNEL — SHADOW NARRATOR & ACTIVE GM DIALOGUE",
        "",
        "> **Rolling Context Window**: Maximum 5 messages from each agent (10 messages total max).",
        "> Older entries are automatically pruned on append to prevent prompt bloat and keep directives focused.",
        "",
        "---",
        ""
    ]

    for msg in messages:
        msg_id = msg.get("id", "MSG")
        sender = normalize_sender(msg.get("sender", "SHADOW"))
        recipient = normalize_sender(msg.get("recipient", "ACTIVE" if sender == "SHADOW" else "SHADOW"))
        turn = msg.get("turn")
        timestamp = msg.get("timestamp") or ""

        header_parts = [f"[{msg_id}] {sender} -> {recipient}"]
        if turn is not None:
            header_parts.append(f"Turn {turn}")
        if timestamp:
            header_parts.append(str(timestamp))

        header_str = " | ".join(header_parts)
        lines.append(f"### {header_str}")
        lines.append(msg.get("content", "").strip())
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


class AgentChannelManager:
    """
    Manages reading, posting to, and pruning the inter-narrator communication channel
    for a given campaign directory.
    """
    def __init__(self, campaign_dir: str):
        self.campaign_dir = campaign_dir
        self.ideas_dir = os.path.join(campaign_dir, "IDEAS")
        self.md_path = os.path.join(self.ideas_dir, CHANNEL_FILENAME_MD)
        self.json_path = os.path.join(self.ideas_dir, CHANNEL_FILENAME_JSON)

    def load_messages(self) -> List[Dict[str, Any]]:
        """Loads messages from JSON if available, else parses Markdown."""
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("messages", [])
            except Exception:
                pass

        if os.path.exists(self.md_path):
            try:
                with open(self.md_path, "r", encoding="utf-8") as f:
                    return parse_channel_markdown(f.read())
            except Exception:
                pass

        return []

    def post_message(
        self,
        sender: str,
        content: str,
        turn: Optional[int] = None,
        recipient: Optional[str] = None,
        msg_id: Optional[str] = None,
        max_per_sender: int = DEFAULT_MAX_PER_SENDER
    ) -> List[Dict[str, Any]]:
        """
        Appends a new message from sender to the channel, automatically prunes to the
        last `max_per_sender` messages per role, and persists to disk.
        """
        os.makedirs(self.ideas_dir, exist_ok=True)
        messages = self.load_messages()

        norm_sender = normalize_sender(sender)
        norm_recipient = normalize_sender(recipient or ("ACTIVE" if norm_sender == "SHADOW" else "SHADOW"))

        if not msg_id:
            msg_num = len(messages) + 1
            msg_id = f"MSG-{msg_num:03d}"

        timestamp = datetime.now(timezone.utc).isoformat()

        new_msg = {
            "id": msg_id,
            "sender": norm_sender,
            "recipient": norm_recipient,
            "turn": turn,
            "timestamp": timestamp,
            "content": content.strip()
        }

        messages.append(new_msg)
        pruned_messages = prune_channel_messages(messages, max_per_sender=max_per_sender)

        # Write to Markdown
        md_content = format_channel_markdown(pruned_messages, campaign_id=os.path.basename(self.campaign_dir))
        with open(self.md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        # Write to JSON for structured tooling
        json_data = {
            "schema_version": 1,
            "campaign_id": os.path.basename(self.campaign_dir),
            "rolling_window_limit_per_role": max_per_sender,
            "updated_at": timestamp,
            "messages": pruned_messages
        }
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)

        return pruned_messages

    def get_latest_directives(self, for_role: str = "ACTIVE") -> List[Dict[str, Any]]:
        """Returns the active directives currently addressing `for_role`."""
        messages = self.load_messages()
        norm_role = normalize_sender(for_role)
        return [m for m in messages if normalize_sender(m.get("recipient", "")) == norm_role]
