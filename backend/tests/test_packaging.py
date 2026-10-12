import tempfile
import unittest
from pathlib import Path


class PackagingTests(unittest.TestCase):
    def test_packaging_uses_whitelist_and_never_copies_user_state_or_original_audio(self):
        from scripts.package_product import build_product

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "source"
            for name in (
                "frontend/dist/electron/main.cjs",
                "frontend/dist/renderer/index.html",
                "frontend/desktop/backend_host.py",
                "frontend/package.json",
                "frontend/node_modules/electron/dist/electron.exe",
                "backend/herta_agent/__init__.py",
                "persona/soul.md",
                "knowledge/example.md",
                "scripts/Start-Herta.ps1",
                ".venv/Scripts/python.exe",
                ".venv/Lib/site-packages/_editable_impl_herta_agent.pth",
                ".local/python/runtime/python.exe",
                ".local/desktop/sessions.sqlite3",
                ".local/desktop/settings.json",
                ".local/music/user-imported.wav",
                ".local/voice/private-recording.wav",
                ".env",
                "theHerta/user.pth",
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
            target = root / "release/product"
            result = build_product(
                root,
                target,
                python_runtime=root / ".local/python/runtime",
                include_voice=False,
                embedding=None,
            )
            self.assertTrue((target / "frontend/dist/electron/main.cjs").is_file())
            self.assertNotEqual(
                (target / ".venv/Lib/site-packages/_editable_impl_herta_agent.pth").read_text(),
                "fixture",
            )
            self.assertFalse(list(target.rglob("*.sqlite3")))
            self.assertFalse((target / ".env").exists())
            self.assertFalse((target / "theHerta").exists())
            self.assertFalse((target / ".local/voice/private-recording.wav").exists())
            self.assertGreater(result["files"], 0)
            with self.assertRaises(ValueError):
                build_product(
                    root,
                    root.parent / "outside",
                    python_runtime=root / ".local/python/runtime",
                    include_voice=False,
                    embedding=None,
                )
            with self.assertRaises(ValueError):
                build_product(
                    root,
                    target,
                    python_runtime=root / ".local/python/runtime",
                    include_voice=False,
                    embedding=None,
                )
