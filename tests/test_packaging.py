import os
import unittest
from pathlib import Path
import yaml


class TestPackaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.requirements_path = cls.repo_root / "requirements.txt"
        cls.dockerfile_path = cls.repo_root / "Dockerfile"
        cls.compose_path = cls.repo_root / "docker-compose.yml"
        cls.dockerignore_path = cls.repo_root / ".dockerignore"
        cls.entrypoint_path = cls.repo_root / "scripts" / "entrypoint.sh"

    def test_files_exist(self):
        """Validates all packaging configuration files exist."""
        self.assertTrue(self.requirements_path.is_file(), "requirements.txt should exist")
        self.assertTrue(self.dockerfile_path.is_file(), "Dockerfile should exist")
        self.assertTrue(self.compose_path.is_file(), "docker-compose.yml should exist")
        self.assertTrue(self.dockerignore_path.is_file(), ".dockerignore should exist")
        self.assertTrue(self.entrypoint_path.is_file(), "scripts/entrypoint.sh should exist")

    def test_requirements_txt(self):
        """Validates requirements.txt contains required dependencies."""
        content = self.requirements_path.read_text(encoding="utf-8")
        lines = [line.strip().lower() for line in content.splitlines() if line.strip() and not line.startswith("#")]
        
        has_jsonschema = any(line.startswith("jsonschema") for line in lines)
        has_pyyaml = any(line.startswith("pyyaml") for line in lines)

        self.assertTrue(has_jsonschema, "requirements.txt should require jsonschema")
        self.assertTrue(has_pyyaml, "requirements.txt should require pyyaml")

    def test_dockerfile_directives(self):
        """Validates Dockerfile contains key instructions and directives."""
        content = self.dockerfile_path.read_text(encoding="utf-8")

        self.assertIn("FROM python:3.13-slim", content)
        self.assertIn("WORKDIR /app", content)
        self.assertIn("COPY", content)
        self.assertIn("EXPOSE 8000", content)
        self.assertIn("EXPOSE 3000", content)
        self.assertIn("HEALTHCHECK", content)
        self.assertIn("ENTRYPOINT", content)
        self.assertIn("http://localhost:8000/health", content)

    def test_entrypoint_script(self):
        """Validates scripts/entrypoint.sh structure and command branches."""
        content = self.entrypoint_path.read_text(encoding="utf-8")
        
        self.assertTrue(content.startswith("#!/bin/sh"), "entrypoint.sh must have POSIX sh shebang")
        self.assertIn("engine)", content)
        self.assertIn("ui)", content)
        self.assertIn("all)", content)
        self.assertIn('exec "$@"', content)
        self.assertIn("ENGINE/engine.py", content)
        self.assertIn("http.server 3000", content)

    def test_dockerignore(self):
        """Validates .dockerignore ignores development and cache artifacts."""
        content = self.dockerignore_path.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]

        self.assertIn(".git", lines)
        self.assertIn("__pycache__", lines)
        self.assertIn(".worktrees", lines)

    def test_docker_compose_spec(self):
        """Validates docker-compose.yml structure, services, ports, and commands."""
        with open(self.compose_path, "r", encoding="utf-8") as f:
            compose = yaml.safe_load(f)

        self.assertIsInstance(compose, dict, "Compose spec must parse as a dictionary")
        self.assertIn("services", compose, "Compose spec must contain 'services'")
        services = compose["services"]

        # Engine service
        self.assertIn("engine", services, "Compose spec must contain 'engine' service")
        engine = services["engine"]
        self.assertEqual(engine.get("build"), ".")
        self.assertEqual(engine.get("container_name"), "whimsy-engine")
        self.assertEqual(engine.get("command"), ["engine"])
        self.assertEqual(engine.get("restart"), "unless-stopped")
        self.assertIn("8000:8000", engine.get("ports", []))
        self.assertIn("./CAMPAIGNS:/app/CAMPAIGNS", engine.get("volumes", []))

        # Check engine environment
        env = engine.get("environment")
        if isinstance(env, list):
            self.assertTrue(any("ANTIGRAVITY_PORT=8000" in item for item in env))
            self.assertTrue(any("PYTHONUNBUFFERED=1" in item for item in env))
        elif isinstance(env, dict):
            self.assertEqual(str(env.get("ANTIGRAVITY_PORT")), "8000")
            self.assertEqual(str(env.get("PYTHONUNBUFFERED")), "1")
        else:
            self.fail("Engine environment must be a list or dict")

        # UI service
        self.assertIn("ui", services, "Compose spec must contain 'ui' service")
        ui = services["ui"]
        self.assertEqual(ui.get("build"), ".")
        self.assertEqual(ui.get("container_name"), "whimsy-ui")
        self.assertEqual(ui.get("command"), ["ui"])
        self.assertEqual(ui.get("restart"), "unless-stopped")
        self.assertIn("3000:3000", ui.get("ports", []))

        depends_on = ui.get("depends_on")
        if isinstance(depends_on, list):
            self.assertIn("engine", depends_on)
        elif isinstance(depends_on, dict):
            self.assertIn("engine", depends_on)
        else:
            self.fail("UI depends_on must specify engine")


if __name__ == "__main__":
    unittest.main()
