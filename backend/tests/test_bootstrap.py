import tempfile
import unittest
from pathlib import Path

from herta_agent.rag.service import DEFAULT_KNOWLEDGE


class BootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_builds_once_and_reuses_matching_index(self):
        from herta_agent.bootstrap import ensure_index

        class Embeddings:
            fingerprint = "f" * 64
            model = "fixture"
            calls = 0

            async def embed_documents(self, texts):
                self.calls += 1
                return [[1.0, 0.0, 0.0] for _ in texts]

        embeddings = Embeddings()
        with tempfile.TemporaryDirectory() as directory:
            first = await ensure_index(embeddings, DEFAULT_KNOWLEDGE, Path(directory), prepare=True)
            second = await ensure_index(
                embeddings, DEFAULT_KNOWLEDGE, Path(directory), prepare=True
            )
        self.assertTrue(first["index_ready"])
        self.assertTrue(first["index_built"])
        self.assertFalse(second["index_built"])
        self.assertEqual(first["index_id"], second["index_id"])
        self.assertEqual(embeddings.calls, 1)

    async def test_check_does_not_build_or_send_documents(self):
        from herta_agent.bootstrap import ensure_index

        class Embeddings:
            fingerprint = "f" * 64
            model = "fixture"

            async def embed_documents(self, texts):
                raise AssertionError("read-only check cannot build")

        with tempfile.TemporaryDirectory() as directory:
            result = await ensure_index(
                Embeddings(), DEFAULT_KNOWLEDGE, Path(directory), prepare=False
            )
        self.assertFalse(result["index_ready"])
        self.assertFalse(result["index_built"])

    async def test_offline_bootstrap_never_prepares_remote_embeddings(self):
        from unittest.mock import patch

        from herta_agent.bootstrap import inspect

        class Remote:
            model = "fixture"

            async def embed_documents(self, texts):
                raise AssertionError("offline startup must not send knowledge to remote")

        with patch("herta_agent.bootstrap.create_embeddings", return_value=Remote()):
            report = await inspect(prepare=True, offline=True)
        self.assertFalse(report["index_ready"])
        self.assertEqual(report["rag_error"], "remote_embeddings_disabled")
