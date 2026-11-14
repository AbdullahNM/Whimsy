#!/usr/bin/env python3
"""Tests for Issue #18: itch.io Publishing & Distribution Packaging.

Verifies:
  1. scripts/build_dist.py packaging on template_campaign.
  2. Single self-contained playable .html artifact with all scripts, CSS, and data inlined.
  3. Zip archive containing index.html at root (itch.io HTML5 zip spec).
  4. R9 (Private-campaign safety) assertion failure on multiple campaigns or unauthorized paths.
  5. scripts/itch_meta.py metadata generation (tags, dimensions, mobile-friendly flag).
  6. CLI execution of build_dist.py and itch_meta.py.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.build_dist import (
    build_dist,
    verify_single_campaign_safety,
    CampaignSafetyError,
)
from scripts.itch_meta import generate_itch_metadata


class TestDistBuild(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="whimsy_dist_test_")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_dist_template_campaign(self):
        """Verify build_dist produces index.html, <id>.html, zip, and metadata."""
        out_dir = os.path.join(self.temp_dir, "template_campaign")
        artefacts = build_dist("template_campaign", out_dir=out_dir)

        self.assertIn("index_html", artefacts)
        self.assertIn("named_html", artefacts)
        self.assertIn("zip", artefacts)
        self.assertIn("itch_metadata", artefacts)
        self.assertIn("itch_listing", artefacts)

        self.assertTrue(os.path.isfile(artefacts["index_html"]))
        self.assertTrue(os.path.isfile(artefacts["named_html"]))
        self.assertTrue(os.path.isfile(artefacts["zip"]))
        self.assertTrue(os.path.isfile(artefacts["itch_metadata"]))
        self.assertTrue(os.path.isfile(artefacts["itch_listing"]))

    def test_zip_contains_index_html_at_root(self):
        """Verify the zip archive contains index.html at root per itch.io HTML5 upload spec."""
        out_dir = os.path.join(self.temp_dir, "template_campaign")
        artefacts = build_dist("template_campaign", out_dir=out_dir)
        zip_path = artefacts["zip"]

        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("index.html", namelist, "Zip must contain index.html")
            
            # Verify index.html is located strictly at the root (no folder prefix)
            for name in namelist:
                if name.endswith("index.html"):
                    self.assertEqual(name, "index.html", "index.html must be located at zip root without folder nesting")

            # Verify index.html content inside zip matches generated self-contained html
            with zf.open("index.html") as f_in_zip:
                zip_content = f_in_zip.read().decode("utf-8")
            
            with open(artefacts["index_html"], "r", encoding="utf-8") as f_disk:
                disk_content = f_disk.read()

            self.assertEqual(zip_content, disk_content)

    def test_single_file_html_zero_external_dependencies(self):
        """Verify the single .html file inlines all CSS, scripts, and campaign data."""
        out_dir = os.path.join(self.temp_dir, "template_campaign")
        artefacts = build_dist("template_campaign", out_dir=out_dir)

        with open(artefacts["index_html"], "r", encoding="utf-8") as f:
            html = f.read()

        # Zero external script or stylesheet links
        self.assertNotIn('<link rel="stylesheet" href="styles.css">', html)
        self.assertNotIn('<script src="app.js"></script>', html)
        self.assertNotIn('<script src="core/deterministic_core.js"></script>', html)
        self.assertNotIn('<script src="storage/indexeddb.js"></script>', html)

        # Inlined styles and scripts
        self.assertIn("<style>", html)
        self.assertIn("/* Whimsy Styles */", html)
        self.assertIn("window.__INLINED_BUILD__ = true;", html)
        self.assertIn('window.__BUNDLED_CAMPAIGN_ID__ = "template_campaign"', html)
        self.assertIn("window.__CAMPAIGN_CONFIGS__", html)
        self.assertIn("window.__GAMEPLAY_MANIFEST__", html)
        self.assertIn("window.__WORLD_BIBLE_DATA__", html)

        # Core runtime objects present
        self.assertIn("DeterministicCore", html)
        self.assertIn("WhimsyStorage", html)
        self.assertIn("TieredNarrator", html)

    def test_r9_assertion_fails_on_multiple_campaigns(self):
        """Enforces R9: Build-time assertion must fail if multiple campaign IDs are specified."""
        # Comma-separated
        with self.assertRaises(AssertionError):
            build_dist("template_campaign,other_campaign", out_dir=self.temp_dir)

        # Space-separated
        with self.assertRaises(AssertionError):
            build_dist("campaign_one campaign_two", out_dir=self.temp_dir)

        # Non-string list type
        with self.assertRaises(AssertionError):
            build_dist(["template_campaign", "other_campaign"], out_dir=self.temp_dir)

        # verify_single_campaign_safety directly with multiple configs
        with self.assertRaises(AssertionError):
            verify_single_campaign_safety(
                campaign_id="template_campaign",
                campaign_configs={"template_campaign": {}, "second_campaign": {}},
                gameplay_manifest={"template_campaign": {}},
            )

        # verify_single_campaign_safety directly with multiple manifests
        with self.assertRaises(AssertionError):
            verify_single_campaign_safety(
                campaign_id="template_campaign",
                campaign_configs={"template_campaign": {}},
                gameplay_manifest={"template_campaign": {}, "second_campaign": {}},
            )

    def test_r9_assertion_fails_on_unauthorized_paths(self):
        """Enforces R9: Build-time assertion must fail if unauthorized paths or traversals are passed."""
        # Directory traversal
        with self.assertRaises(AssertionError):
            build_dist("../../private_campaign", out_dir=self.temp_dir)

        with self.assertRaises(AssertionError):
            build_dist("../secret", out_dir=self.temp_dir)

        # Subdirectory / path separators
        with self.assertRaises(AssertionError):
            build_dist("template_campaign/subfolder", out_dir=self.temp_dir)

        # Non-existent campaign
        with self.assertRaises(AssertionError):
            build_dist("non_existent_unauthorized_campaign_999", out_dir=self.temp_dir)

        # verify_single_campaign_safety with empty id
        with self.assertRaises(AssertionError):
            verify_single_campaign_safety(
                campaign_id="",
                campaign_configs={},
                gameplay_manifest={},
            )

    def test_r9_assertion_fails_on_leaked_campaign_or_system_paths(self):
        """Enforces R9: Assertion must fail if sibling campaign or host path is leaked."""
        # Mismatched campaign ID in config
        with self.assertRaises(AssertionError):
            verify_single_campaign_safety(
                campaign_id="template_campaign",
                campaign_configs={"unauthorized_private_id": {}},
                gameplay_manifest={"template_campaign": {}},
            )

        # Leaked host path in HTML payload
        with self.assertRaises(AssertionError):
            verify_single_campaign_safety(
                campaign_id="template_campaign",
                campaign_configs={"template_campaign": {}},
                gameplay_manifest={"template_campaign": {}},
                html_content="<script>var leak = 'C:\\\\Users\\\\developer\\\\secret_campaign';</script>",
            )

    def test_itch_metadata_generation(self):
        """Verify scripts/itch_meta.py produces complete metadata and formatted listing."""
        out_dir = os.path.join(self.temp_dir, "meta_test")
        meta, md = generate_itch_metadata("template_campaign", out_dir=out_dir)

        # Check metadata dictionary
        self.assertEqual(meta["campaign_id"], "template_campaign")
        self.assertIn("title", meta)
        self.assertTrue(len(meta["title"]) > 0)
        self.assertIn("tagline", meta)
        self.assertTrue(len(meta["tagline"]) > 0)
        self.assertLessEqual(len(meta["tagline"]), 100, "Tagline should be within 100 characters")
        self.assertIn("description", meta)
        self.assertIn("genre", meta)

        # Required tags: interactive-fiction, text-based, cyoa, plus genre tags
        tags = meta["tags"]
        self.assertIn("interactive-fiction", tags)
        self.assertIn("text-based", tags)
        self.assertIn("cyoa", tags)
        self.assertIn("adventure", tags)

        # Embed dimensions and mobile flag
        embed = meta["embed"]
        self.assertEqual(embed["width"], 1024)
        self.assertEqual(embed["height"], 768)
        self.assertTrue(embed["responsive"])
        self.assertTrue(meta["mobile_friendly"])
        self.assertEqual(meta["kind_of_project"], "html")

        # Check generated files
        meta_json_path = os.path.join(out_dir, "itch_metadata.json")
        meta_md_path = os.path.join(out_dir, "ITCH_LISTING.md")
        self.assertTrue(os.path.isfile(meta_json_path))
        self.assertTrue(os.path.isfile(meta_md_path))

        with open(meta_json_path, "r", encoding="utf-8") as f:
            disk_meta = json.load(f)
        self.assertEqual(disk_meta["title"], meta["title"])

        with open(meta_md_path, "r", encoding="utf-8") as f:
            disk_md = f.read()
        self.assertIn("# itch.io Project Listing:", disk_md)
        self.assertIn("interactive-fiction", disk_md)
        self.assertIn("1024", disk_md)
        self.assertIn("768", disk_md)

    def test_cli_execution(self):
        """Verify build_dist.py and itch_meta.py can be invoked directly from the CLI."""
        dist_out = os.path.join(self.temp_dir, "cli_dist")
        meta_out = os.path.join(self.temp_dir, "cli_meta")

        # 1. Test build_dist.py CLI
        res_build = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "build_dist.py"),
                "--campaign", "template_campaign",
                "--out", dist_out,
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(res_build.returncode, 0, f"build_dist CLI failed: {res_build.stderr}")
        self.assertTrue(os.path.isfile(os.path.join(dist_out, "index.html")))
        self.assertTrue(os.path.isfile(os.path.join(dist_out, "template_campaign.zip")))

        # 2. Test itch_meta.py CLI
        res_meta = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "scripts", "itch_meta.py"),
                "--campaign", "template_campaign",
                "--out", meta_out,
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(res_meta.returncode, 0, f"itch_meta CLI failed: {res_meta.stderr}")
        self.assertTrue(os.path.isfile(os.path.join(meta_out, "itch_metadata.json")))
        self.assertTrue(os.path.isfile(os.path.join(meta_out, "ITCH_LISTING.md")))


if __name__ == "__main__":
    unittest.main()
