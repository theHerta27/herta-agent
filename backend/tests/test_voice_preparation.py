import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_voice import create_manifest


class VoicePreparationTests(unittest.TestCase):
    def test_repreparing_manifest_keeps_stable_valid_hashes_without_hashing_itself(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "model.bin").write_bytes(b"public model")
            first = create_manifest(root, {"revision": "asr"}, {"revision": "tts"})
            second = create_manifest(root, {"revision": "asr"}, {"revision": "tts"})
            self.assertEqual(first, second)
            self.assertEqual(
                second["files"], {"model.bin": hashlib.sha256(b"public model").hexdigest()}
            )
