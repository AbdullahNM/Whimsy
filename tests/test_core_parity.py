#!/usr/bin/env python3
"""
tests/test_core_parity.py
=========================
Equivalence test suite asserting byte-identical Outcome JSON parity between
Python (ENGINE/deterministic_core.py) and JavaScript (UI/core/deterministic_core.js)
over the shared fixture corpus in tests/fixtures/outcomes/.

Adheres strictly to Issue #14: R4, R5.
"""

import glob
import json
import os
import subprocess
import sys
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ENGINE.deterministic_core import Core


class TestCoreParity(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.join(ROOT_DIR, "tests", "fixtures", "outcomes")
        self.js_core_path = os.path.join(ROOT_DIR, "UI", "core", "deterministic_core.js")
        self.assertTrue(os.path.isdir(self.fixtures_dir), f"Fixtures directory not found: {self.fixtures_dir}")
        self.assertTrue(os.path.isfile(self.js_core_path), f"JS core not found: {self.js_core_path}")

    def test_fixtures_exist(self):
        fixture_files = sorted(glob.glob(os.path.join(self.fixtures_dir, "*.json")))
        self.assertGreaterEqual(len(fixture_files), 10, "Expected at least 10 fixtures in the shared corpus")

    def test_python_and_node_parity_over_all_fixtures(self):
        fixture_files = sorted(glob.glob(os.path.join(self.fixtures_dir, "*.json")))

        node_script = """
const fs = require('fs');
const { Core } = require('./UI/core/deterministic_core.js');

const raw = fs.readFileSync(0, 'utf8');
const fixture = JSON.parse(raw);
const outcome = Core.resolve(fixture.state, fixture.action, fixture.config);
process.stdout.write(outcome.toJson());
"""

        for fix_path in fixture_files:
            fix_name = os.path.basename(fix_path)
            with self.subTest(fixture=fix_name):
                with open(fix_path, "r", encoding="utf-8") as f:
                    fix_content = f.read()
                    fix_data = json.loads(fix_content)

                state = fix_data["state"]
                action = fix_data["action"]
                config = fix_data.get("config", {})

                # 1. Resolve in Python
                outcome_py = Core.resolve(state, action, config)
                py_json = outcome_py.to_json()

                # 2. Resolve in Node.js via stdin
                proc = subprocess.run(
                    ["node", "-e", node_script],
                    input=fix_content,
                    cwd=ROOT_DIR,
                    capture_output=True,
                    text=True,
                    check=False
                )
                self.assertEqual(
                    proc.returncode, 0,
                    f"Node execution failed for {fix_name}:\n{proc.stderr}"
                )
                js_json = proc.stdout

                # 3. Assert Byte-Identical JSON Parity
                self.assertEqual(
                    py_json, js_json,
                    f"Python and Node produced divergent JSON for fixture {fix_name}!\n"
                    f"Python:\n{py_json}\n\nNode:\n{js_json}"
                )

                # 4. Assert Expected Outcome Parity
                if "expected_outcome" in fix_data:
                    expected_json = json.dumps(fix_data["expected_outcome"], indent=2, sort_keys=True, ensure_ascii=False)
                    self.assertEqual(
                        py_json, expected_json,
                        f"Python outcome diverged from expected_outcome in {fix_name}"
                    )


if __name__ == "__main__":
    unittest.main()
