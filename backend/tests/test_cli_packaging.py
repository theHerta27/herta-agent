"""Keep the CLI install independent of optional desktop/model dependencies."""

import re
import tomllib
import unittest
from pathlib import Path


class CLIPackagingTests(unittest.TestCase):
    def test_cli_install_requires_only_core_and_terminal_libraries(self):
        config = tomllib.loads(
            (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
        )
        project = config["project"]
        names = {re.split(r"[<>=\[]", item)[0] for item in project["dependencies"]}
        self.assertEqual(names, {"httpx", "pydantic", "rich", "prompt-toolkit"})
        desktop = project["optional-dependencies"].get("desktop", ())
        self.assertIn("fastapi", {re.split(r"[<>=\[]", item)[0] for item in desktop})
        self.assertEqual(project["scripts"]["herta-agent"], "herta_agent.__main__:main")


if __name__ == "__main__":
    unittest.main()
