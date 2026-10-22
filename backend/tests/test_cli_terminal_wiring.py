"""Product entry uses the new presenter only for terminal interaction."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TerminalWiringTests(unittest.TestCase):
    def test_sigint_after_terminal_input_cleans_model_and_tool_then_accepts_next_turn(self):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(Path(__file__).with_name("terminal_interrupt_probe.py")),
            ],
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CLEANED:model", result.stdout)
        self.assertIn("CLEANED:tool", result.stdout)
        self.assertIn("RESUMED:turns=3", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_real_entry_selects_readable_terminal_output_and_hides_diagnostics(self):
        from herta_agent.cli import main

        class TerminalBuffer(io.StringIO):
            def isatty(self):
                return True

        output = TerminalBuffer()
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("sys.stdin", TerminalBuffer()),
            patch("sys.stdout", output),
            patch("sys.stderr", io.StringIO()),
            patch.dict(os.environ, {"TERM": "xterm-256color"}),
        ):
            main(
                ["--repo", folder, "--data-dir", str(Path(folder) / "state"), "--message", "hello"]
            )
        text = output.getvalue()
        self.assertIn("Herta Agent", text)
        self.assertIn("离线演示", text)
        self.assertIn("hello", text)
        self.assertNotIn("[steps=", text)
        self.assertNotIn("[session=", text)
        self.assertNotIn("sessions.sqlite3", text)

    def test_dumb_terminal_uses_plain_input_and_approval(self):
        from herta_agent.cli import main

        class TerminalBuffer(io.StringIO):
            def isatty(self):
                return True

        output = TerminalBuffer()
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"TERM": "dumb"}),
            patch("sys.stdin", TerminalBuffer()),
            patch("sys.stdout", output),
            patch("sys.stderr", io.StringIO()),
            patch("herta_agent.terminal_ui.TerminalUI") as ui,
        ):
            main(["--repo", folder, "--message", "hello"])
        ui.assert_not_called()
        self.assertIn("Assistant:", output.getvalue())
        self.assertNotIn("\x1b", output.getvalue())

    def test_explicit_plain_remains_usable_in_pipes_without_escape_codes(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("HERTA_") and k != "DEEPSEEK_API_KEY"
        }
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                "-m",
                "herta_agent",
                "--plain",
                "--message",
                "hello",
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("离线演示", result.stdout)
        self.assertNotIn("\x1b", result.stdout)


if __name__ == "__main__":
    unittest.main()
