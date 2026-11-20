import unittest
from pathlib import Path


class TestDocumentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.quickstart_path = cls.repo_root / "QUICKSTART.md"
        cls.readme_path = cls.repo_root / "README.md"

    def test_quickstart_exists(self):
        """Validates that QUICKSTART.md exists in the repository root."""
        self.assertTrue(self.quickstart_path.is_file(), "QUICKSTART.md should exist in repo root")

    def test_quickstart_content_sections(self):
        """Validates that QUICKSTART.md covers Docker Compose, native execution, dependencies, and testing."""
        content = self.quickstart_path.read_text(encoding="utf-8")

        # Docker Compose checks
        self.assertIn("docker compose up --build", content)
        self.assertIn("http://localhost:8000", content)
        self.assertIn("http://localhost:3000", content)
        self.assertIn("./CAMPAIGNS:/app/CAMPAIGNS", content)
        self.assertIn("docker compose down", content)
        self.assertIn("docker compose logs", content)

        # Native Local Execution checks
        self.assertIn("Method 2: Direct Local Execution", content)
        self.assertIn("git clone", content)
        self.assertIn("venv", content)
        self.assertIn("Activate.ps1", content)
        self.assertIn("activate", content)
        self.assertIn("requirements.txt", content)
        self.assertIn("pip install -r requirements.txt", content)
        self.assertIn("python ENGINE/engine.py", content)
        self.assertIn("python -m http.server 3000 --directory UI", content)

        # Testing commands
        self.assertIn("python -m unittest discover -s tests", content)
        self.assertIn("node --test tests/*.js", content)

        # Standalone / Dist Build checks
        self.assertIn("scripts/build_dist.py", content)
        self.assertIn("--campaign template_campaign", content)
        self.assertIn("dist/template_campaign/index.html", content)

        # Environment & Troubleshooting
        self.assertIn("ANTIGRAVITY_PORT", content)
        self.assertIn("PYTHONUNBUFFERED", content)
        self.assertIn("Troubleshooting", content)
        self.assertIn("8000", content)
        self.assertIn("3000", content)

    def test_readme_references(self):
        """Validates that README.md references QUICKSTART.md, docker-compose.yml, and requirements.txt."""
        content = self.readme_path.read_text(encoding="utf-8")

        self.assertIn("QUICKSTART.md", content, "README.md must reference QUICKSTART.md")
        self.assertIn("docker-compose.yml", content, "README.md must reference docker-compose.yml")
        self.assertIn("docker compose up --build", content, "README.md must feature docker compose up --build")
        self.assertIn("requirements.txt", content, "README.md must reference requirements.txt")


if __name__ == "__main__":
    unittest.main()
