import json
import os
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path


@unittest.skipUnless(os.name == "nt", "Windows launcher")
class DesktopStartGuardTests(unittest.TestCase):
    def check(self, *, stale, folder_entry=False, unrelated=False):
        with tempfile.TemporaryDirectory(prefix="Herta 启动 空格 ") as directory:
            root = Path(directory)
            entry = root / "frontend/dist/electron/main.cjs"
            renderer = root / "frontend/dist/renderer/index.html"
            for file in (entry, renderer):
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("current build")
            built = datetime.now(UTC) - timedelta(hours=1)
            for file in (entry, renderer):
                os.utime(file, (built.timestamp(), built.timestamp()))
            process = {
                "ProcessId": 123,
                "ExecutablePath": str(root / "frontend/node_modules/electron/dist/electron.exe"),
                "CommandLine": f'electron.exe "{root / "frontend" if folder_entry else entry}"',
                "CreationDate": (built + timedelta(hours=-1 if stale else 1)).isoformat(),
            }
            if unrelated:
                process["CommandLine"] += " --type=renderer"
            helper = Path(__file__).resolve().parents[2] / "scripts/Test-HertaDesktopFresh.ps1"
            payload = json.dumps([process]).replace("'", "''")
            command = (
                "$ErrorActionPreference='Stop'; "
                f". '{helper}'; "
                f"function Get-CimInstance {{ ConvertFrom-Json '{payload}' }}; "
                f"try {{ Assert-HertaDesktopFresh -Root '{root}'; 'allowed' }} "
                "catch { 'blocked:' + $_.Exception.Message }"
            )
            return subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
            )

    def test_stale_direct_and_folder_launches_require_tray_exit(self):
        for folder_entry in (False, True):
            with self.subTest(folder_entry=folder_entry):
                result = self.check(stale=True, folder_entry=folder_entry)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("blocked:", result.stdout)
                self.assertIn("Exit Herta", result.stdout)

    def test_current_instance_can_be_activated(self):
        result = self.check(stale=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("allowed", result.stdout)

    def test_child_renderer_does_not_block_launch(self):
        result = self.check(stale=True, unrelated=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("allowed", result.stdout)
