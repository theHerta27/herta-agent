import os
import subprocess
import sys
import unittest


class CLITests(unittest.TestCase):
    def test_single_message_sigint_exits_130_after_cleanup(self) -> None:
        from pathlib import Path

        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("cli_interrupt_probe.py")), "--single"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, 130, result.stderr)
        self.assertIn("CLEANED:model", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_tools_demo_success_and_timeout(self) -> None:
        success = self.invoke("--demo-tools", "--message", "你好")
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertIn("[steps=2]", success.stdout)
        self.assertIn('"text": "你好"', success.stdout)
        timeout = self.invoke(
            "--demo-tools", "--demo-delay", "1", "--tool-timeout", "0.02", "--message", "你好"
        )
        self.assertEqual(timeout.returncode, 0, timeout.stderr)
        self.assertIn('"code": "timeout"', timeout.stdout)

    def test_sigint_during_model_and_tool_preserves_interactive_session(self) -> None:
        from pathlib import Path

        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("cli_interrupt_probe.py"))],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CLEANED:model", result.stdout)
        self.assertIn("CLEANED:tool", result.stdout)
        self.assertIn("RESUMED:turns=3", result.stdout)

    def invoke(self, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items() if not key.startswith("HERTA_")}
        env.pop("PYTHONIOENCODING", None)
        return subprocess.run(
            [sys.executable, "-m", "herta_agent", *args],
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=10,
            check=False,
        )

    def test_default_mode_is_offline_and_runnable_without_settings(self) -> None:
        result = self.invoke("--message", "hello")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("离线演示", result.stdout)
        self.assertIn("steps=1", result.stdout)

    def test_interactive_mode_retains_history_until_exit(self) -> None:
        result = self.invoke(input_text="第一句\n第二句\n/exit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("第 2 轮", result.stdout)
        self.assertIn("收到：第二句", result.stdout)

    def test_real_provider_requires_explicit_configuration(self) -> None:
        result = self.invoke("--provider", "openai", "--message", "hello")
        self.assertEqual(result.returncode, 1)
        self.assertIn("HERTA_BASE_URL", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_budget_fails_before_calling_demo(self) -> None:
        result = self.invoke("--max-steps", "0", "--message", "hello")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Assistant:", result.stdout)
