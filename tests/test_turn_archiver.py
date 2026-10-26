import unittest
import os
import shutil
import tempfile
import glob

from ENGINE.turn_archiver import (
    record_turn,
    load_active_turns,
    get_turn_number,
    MAX_ACTIVE_TURNS,
    ACTIVE_BASELINE_TURNS,
    ARCHIVE_BATCH_SIZE
)

class TestTurnArchiverBatching(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.campaign_dir = os.path.join(self.test_dir, "test_camp")
        os.makedirs(self.campaign_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_batch_archival_hysteresis(self):
        active_dir = os.path.join(self.campaign_dir, "TURNS", "ACTIVE")
        archive_dir = os.path.join(self.campaign_dir, "TURNS", "ARCHIVE")

        # 1. Record 19 turns - none should be archived yet
        for i in range(1, 20):
            record_turn(self.campaign_dir, i, f"Action {i}", f"Response {i}")

        active_files = glob.glob(os.path.join(active_dir, "turn_*.md"))
        archive_files = glob.glob(os.path.join(archive_dir, "turn_*.md"))
        self.assertEqual(len(active_files), 19)
        self.assertEqual(len(archive_files), 0)

        # 2. Record Turn 20 - should trigger batch archive of oldest 5 (Turns 1-5)
        record_turn(self.campaign_dir, 20, "Action 20", "Response 20")

        active_files = sorted(glob.glob(os.path.join(active_dir, "turn_*.md")), key=get_turn_number)
        archive_files = sorted(glob.glob(os.path.join(archive_dir, "turn_*.md")), key=get_turn_number)
        
        self.assertEqual(len(active_files), 15)
        self.assertEqual(len(archive_files), 5)
        self.assertEqual(get_turn_number(active_files[0]), 6)
        self.assertEqual(get_turn_number(active_files[-1]), 20)
        self.assertEqual(get_turn_number(archive_files[0]), 1)
        self.assertEqual(get_turn_number(archive_files[-1]), 5)

        # 3. Record Turns 21-24 - no moves should occur, active grows from 15 to 19
        for i in range(21, 25):
            record_turn(self.campaign_dir, i, f"Action {i}", f"Response {i}")

        active_files = glob.glob(os.path.join(active_dir, "turn_*.md"))
        archive_files = glob.glob(os.path.join(archive_dir, "turn_*.md"))
        self.assertEqual(len(active_files), 19)
        self.assertEqual(len(archive_files), 5)

        # 4. Record Turn 25 - triggers next batch archive of 5 (Turns 6-10)
        record_turn(self.campaign_dir, 25, "Action 25", "Response 25")

        active_files = sorted(glob.glob(os.path.join(active_dir, "turn_*.md")), key=get_turn_number)
        archive_files = sorted(glob.glob(os.path.join(archive_dir, "turn_*.md")), key=get_turn_number)
        self.assertEqual(len(active_files), 15)
        self.assertEqual(len(archive_files), 10)
        self.assertEqual(get_turn_number(active_files[0]), 11)
        self.assertEqual(get_turn_number(active_files[-1]), 25)

if __name__ == "__main__":
    unittest.main()
