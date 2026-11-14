"""tests/test_browser_runtime.py
==============================
Python test suite for Issue #17: Browser-Playable Runtime with No Backend Required.

Verifies:
- R1 & R2: Static hosting suitability (GitHub Pages / itch.io) with zero backend dependency.
- R4: Mobile touch target ergonomics (44x44px minimum) and landscape/portrait media rules.
- R5: Service worker pre-cache asset completeness and Cache-First strategy.
- R3 & R9: Static campaign bundle and manifest integrity.
"""
import json
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_DIR = os.path.join(ROOT, "UI")


class TestBrowserRuntimeStaticBundle(unittest.TestCase):
    def test_static_manifests_exist_and_are_valid(self):
        """Verify that bundled manifests required for offline play exist and parse cleanly."""
        manifest_files = [
            "campaign_configs.json",
            "gameplay_manifest.json",
            "world_bible_data.json",
            "manifest.json"
        ]
        for filename in manifest_files:
            filepath = os.path.join(UI_DIR, filename)
            self.assertTrue(os.path.isfile(filepath), f"Manifest file missing: {filename}")
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertIsNotNone(data, f"Manifest parsed as None: {filename}")

    def test_service_worker_asset_cache_completeness(self):
        """Verify that all assets declared in sw.js ASSETS_TO_CACHE exist in UI directory."""
        sw_path = os.path.join(UI_DIR, "sw.js")
        self.assertTrue(os.path.isfile(sw_path), "UI/sw.js missing")

        with open(sw_path, "r", encoding="utf-8") as f:
            sw_content = f.read()

        # Extract ASSETS_TO_CACHE list
        m = re.search(r"const\s+ASSETS_TO_CACHE\s*=\s*\[([\s\S]*?)\];", sw_content)
        self.assertIsNotNone(m, "ASSETS_TO_CACHE declaration not found in sw.js")

        assets = [
            line.strip().strip("'\",")
            for line in m.group(1).split("\n")
            if line.strip().strip("'\",") and not line.strip().startswith("//")
        ]

        # Verify strategy is cache-first
        self.assertIn("caches.match", sw_content, "Service worker must implement cache checking")
        self.assertIn("cyoa-engine-v17", sw_content, "Service worker cache name should reflect updated version")

        for asset in assets:
            if asset in ["./", ""]:
                continue
            clean_path = asset.lstrip("./").replace("/", os.sep)
            full_path = os.path.join(UI_DIR, clean_path)
            self.assertTrue(os.path.exists(full_path), f"Service worker cached asset does not exist: {clean_path}")

    def test_index_html_script_order_and_elements(self):
        """Verify index.html includes runtime scripts, tier selector, and save tools."""
        html_path = os.path.join(UI_DIR, "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Check script tags
        required_scripts = [
            "core/deterministic_core.js",
            "storage/indexeddb.js",
            "narrator/authored_narrator.js",
            "narrator/local_narrator.js",
            "narrator/cloud_narrator.js",
            "narrator/tiered_narrator.js",
            "app.js"
        ]

        last_pos = -1
        for script in required_scripts:
            pos = html.find(script)
            self.assertNotEqual(pos, -1, f"Missing script reference in index.html: {script}")
            self.assertGreater(pos, last_pos, f"Script loaded out of order: {script}")
            last_pos = pos

        # Check UI elements for Issue #17
        self.assertIn('id="sync-status"', html)
        self.assertIn('status-indexeddb', html)
        self.assertIn('id="narration-tier-select"', html)
        self.assertIn('id="export-save-btn"', html)
        self.assertIn('id="import-save-btn"', html)

    def test_mobile_touch_targets_and_responsive_css(self):
        """Verify styles.css enforces WCAG minimum touch targets (44px) and mobile landscape rules."""
        css_path = os.path.join(UI_DIR, "styles.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()

        self.assertIn(".status-indexeddb", css)
        self.assertIn("min-height: 44px", css, "WCAG 44px minimum touch target height required")
        self.assertIn("touch-action: manipulation", css, "Touch action optimization required")
        self.assertIn("orientation: landscape", css, "Landscape orientation media query required")


if __name__ == "__main__":
    unittest.main()
