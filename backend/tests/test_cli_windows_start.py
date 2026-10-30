"""Actual Windows PowerShell 5.1 startup and native-pipe encoding, offline only."""

import base64
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREPARE = ROOT / "examples" / "coding-task" / "prepare.py"


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(sys.platform == "win32", "Windows PowerShell compatibility")
class WindowsStartTests(unittest.TestCase):
    def run_script(self, text, *, cwd=None):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("HERTA_") and k != "DEEPSEEK_API_KEY"
        }
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "probe.ps1"
            script.write_text(text, encoding="utf-8-sig")
            return subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                cwd=ROOT if cwd is None else cwd,
                env=env,
                input="\n\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )

    def test_prepare_json_round_trips_chinese_through_legacy_and_utf8_code_pages(self):
        spec = importlib.util.spec_from_file_location("demo_cases", PREPARE.with_name("cases.py"))
        cases = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cases)
        for page in (936, 65001):
            for name in ("checkout", "wordcount"):
                with self.subTest(page=page, case=name):
                    expected = base64.b64encode(cases.TASKS[name].encode()).decode()
                    result = self.run_script(
                        "$ErrorActionPreference='Stop'\n"
                        f"[Console]::OutputEncoding=[Text.Encoding]::GetEncoding({page})\n"
                        f"$p = & {ps_quote(sys.executable)} -B -X utf8 {ps_quote(PREPARE)} "
                        f"--case {name} | ConvertFrom-Json\n"
                        f"$expected=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{expected}'))\n"
                        "if ($p.task -cne $expected) { throw 'Chinese task did not round-trip' }\n"
                        "if (!(Test-Path -LiteralPath $p.project -PathType Container)) "
                        "{ throw 'Missing demo' }\n"
                        "Write-Output 'ROUNDTRIP_OK'\n"
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("ROUNDTRIP_OK", result.stdout)

    def test_case_launcher_prepares_and_runs_offline_from_another_directory(self):
        # Keep the shell's working directory inside the allowed workspace.
        with tempfile.TemporaryDirectory(prefix="herta start ", dir=ROOT / ".local") as folder:
            result = self.run_script(
                "$ErrorActionPreference='Stop'\n"
                f"& {ps_quote(ROOT / 'scripts' / 'Start-CLI.ps1')} -Case checkout -Demo\n",
                cwd=folder,
            )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("checkout-", result.stdout)
        self.assertIn("Assistant:", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_cmd_entry_runs_the_case_and_prints_a_ready_to_copy_check_command(self):
        result = self.run_script(
            "$ErrorActionPreference='Stop'\n"
            f"& {ps_quote(ROOT / '启动CLI.cmd')} -Case checkout -Demo\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Assistant:", result.stdout)
        self.assertIn("check.py'", result.stdout)
        self.assertIn("checkout-", result.stdout)

    def test_normal_launcher_uses_the_current_project_without_a_directory_prompt(self):
        result = self.run_script(
            "$ErrorActionPreference='Stop'\n"
            f"& {ps_quote(ROOT / 'scripts' / 'Start-CLI.ps1')} -Repo . -Demo\n"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("You:", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
