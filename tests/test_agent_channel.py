import os
import shutil
import tempfile
import unittest

from ENGINE.agent_channel import (
    prune_channel_messages,
    parse_channel_markdown,
    format_channel_markdown,
    AgentChannelManager,
    normalize_sender
)
from ENGINE.prompt_assembler import PromptAssembler


class TestAgentChannel(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.campaign_dir = os.path.join(self.test_dir, "CAMPAIGNS", "test_campaign")
        os.makedirs(os.path.join(self.campaign_dir, "IDEAS"), exist_ok=True)
        self.channel_mgr = AgentChannelManager(self.campaign_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_normalize_sender(self):
        self.assertEqual(normalize_sender("shadow"), "SHADOW")
        self.assertEqual(normalize_sender("SHADOW_NARRATOR"), "SHADOW")
        self.assertEqual(normalize_sender("active_gm"), "ACTIVE")
        self.assertEqual(normalize_sender("gm"), "ACTIVE")
        self.assertEqual(normalize_sender("ACTIVE"), "ACTIVE")

    def test_prune_channel_messages_keeps_last_5_per_role(self):
        messages = []
        # Generate 8 shadow messages and 8 active messages
        for i in range(1, 9):
            messages.append({
                "id": f"S-{i}",
                "sender": "SHADOW",
                "recipient": "ACTIVE",
                "turn": i,
                "content": f"Shadow message {i}"
            })
            messages.append({
                "id": f"A-{i}",
                "sender": "ACTIVE",
                "recipient": "SHADOW",
                "turn": i,
                "content": f"Active message {i}"
            })

        self.assertEqual(len(messages), 16)
        pruned = prune_channel_messages(messages, max_per_sender=5)

        # Retains 5 shadow + 5 active = 10 messages total
        self.assertEqual(len(pruned), 10)

        shadow_ids = [m["id"] for m in pruned if m["sender"] == "SHADOW"]
        active_ids = [m["id"] for m in pruned if m["sender"] == "ACTIVE"]

        self.assertEqual(shadow_ids, ["S-4", "S-5", "S-6", "S-7", "S-8"])
        self.assertEqual(active_ids, ["A-4", "A-5", "A-6", "A-7", "A-8"])

    def test_markdown_parsing_and_formatting_roundtrip(self):
        sample_md = (
            "# AGENT CHANNEL — SHADOW NARRATOR & ACTIVE GM DIALOGUE\n\n"
            "> **Rolling Context Window**: Maximum 5 messages from each agent\n\n"
            "---\n\n"
            "### [MSG-001] SHADOW -> ACTIVE | Turn 10 | 2026-11-09T00:00:00Z\n"
            "Directive: Close the courtyard scene.\n\n"
            "---\n\n"
            "### [MSG-002] ACTIVE -> SHADOW | Turn 11 | 2026-11-09T00:05:00Z\n"
            "Scene closed; moving to lower vaults.\n\n"
            "---\n"
        )
        parsed = parse_channel_markdown(sample_md)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["sender"], "SHADOW")
        self.assertEqual(parsed[0]["turn"], 10)
        self.assertEqual(parsed[0]["content"], "Directive: Close the courtyard scene.")
        self.assertEqual(parsed[1]["sender"], "ACTIVE")
        self.assertEqual(parsed[1]["turn"], 11)

        formatted = format_channel_markdown(parsed)
        self.assertIn("### [MSG-001] SHADOW -> ACTIVE | Turn 10", formatted)
        self.assertIn("### [MSG-002] ACTIVE -> SHADOW | Turn 11", formatted)

    def test_manager_post_message_and_automatic_pruning(self):
        # Post 6 messages as Shadow
        for i in range(1, 7):
            self.channel_mgr.post_message(
                sender="SHADOW",
                content=f"Shadow steering directive {i}",
                turn=i
            )

        # Post 6 messages as Active
        for i in range(1, 7):
            self.channel_mgr.post_message(
                sender="ACTIVE",
                content=f"Active progress sync {i}",
                turn=i
            )

        loaded = self.channel_mgr.load_messages()
        self.assertEqual(len(loaded), 10)

        shadow_turns = [m["turn"] for m in loaded if m["sender"] == "SHADOW"]
        active_turns = [m["turn"] for m in loaded if m["sender"] == "ACTIVE"]

        self.assertEqual(shadow_turns, [2, 3, 4, 5, 6])
        self.assertEqual(active_turns, [2, 3, 4, 5, 6])

        # Verify files were persisted
        self.assertTrue(os.path.exists(self.channel_mgr.md_path))
        self.assertTrue(os.path.exists(self.channel_mgr.json_path))

    def test_prompt_assembler_loads_agent_channel(self):
        self.channel_mgr.post_message(
            sender="SHADOW",
            content="Ensure Delta: 0 progression during archive search.",
            turn=45
        )
        assembler = PromptAssembler(self.test_dir)
        channel_text = assembler.load_agent_channel("test_campaign")
        self.assertIn("AGENT_CHANNEL.MD", channel_text)
        self.assertIn("Ensure Delta: 0 progression", channel_text)

    def test_channel_mode_flag_and_file_fallback(self):
        # Default mode is strictly 'file'
        mgr_default = AgentChannelManager(self.campaign_dir)
        self.assertEqual(mgr_default.channel_mode, "file")

        # Explicit mode flag 'hybrid'
        mgr_hybrid = AgentChannelManager(self.campaign_dir, channel_mode="hybrid")
        self.assertEqual(mgr_hybrid.channel_mode, "hybrid")

        # In hybrid mode, posting a message updates memory AND flushes to file fallback
        mgr_hybrid.post_message(
            sender="SHADOW",
            content="Hybrid mode directive.",
            turn=10
        )
        self.assertTrue(os.path.exists(mgr_hybrid.md_path))
        with open(mgr_hybrid.md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        self.assertIn("Hybrid mode directive.", md_content)

        # File reader still loads it perfectly
        mgr_file = AgentChannelManager(self.campaign_dir, channel_mode="file")
        loaded = mgr_file.load_messages()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["content"], "Hybrid mode directive.")


if __name__ == "__main__":
    unittest.main()
