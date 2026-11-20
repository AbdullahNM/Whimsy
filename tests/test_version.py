"""Tests for repository and engine version metadata."""

import re
import unittest
from pathlib import Path

import ENGINE


class TestVersion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.version_file = cls.repo_root / "VERSION"

    def test_version_file_exists(self):
        """Validates that VERSION file exists at repo root."""
        self.assertTrue(self.version_file.is_file(), "VERSION file must exist at repo root")

    def test_version_file_content(self):
        """Validates that VERSION file contains '0.1.0'."""
        content = self.version_file.read_text(encoding="utf-8").strip()
        self.assertEqual(content, "0.1.0", f"VERSION file should contain '0.1.0', got '{content}'")

    def test_engine_version_matches(self):
        """Validates that ENGINE.__version__ is equal to the content of VERSION."""
        file_version = self.version_file.read_text(encoding="utf-8").strip()
        self.assertTrue(hasattr(ENGINE, "__version__"), "ENGINE module must define __version__")
        self.assertEqual(
            ENGINE.__version__,
            file_version,
            f"ENGINE.__version__ ({ENGINE.__version__}) must equal VERSION file ({file_version})"
        )
        self.assertEqual(ENGINE.__version__, "0.1.0")

    def test_semver_format(self):
        """Validates that the version string conforms to SemVer format (major.minor.patch)."""
        file_version = self.version_file.read_text(encoding="utf-8").strip()
        semver_regex = (
            r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
            r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
            r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
        )
        self.assertRegex(file_version, semver_regex, f"Version '{file_version}' does not conform to SemVer")
        self.assertRegex(
            ENGINE.__version__,
            semver_regex,
            f"ENGINE.__version__ '{ENGINE.__version__}' does not conform to SemVer"
        )

        parts = file_version.split(".")
        self.assertEqual(len(parts), 3, f"Expected 3 components (major.minor.patch), got {len(parts)}")
        for part in parts:
            self.assertTrue(part.isdigit(), f"SemVer component '{part}' must be digits")


if __name__ == "__main__":
    unittest.main()
