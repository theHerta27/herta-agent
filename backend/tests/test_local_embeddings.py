import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from herta_agent.rag.embeddings import (
    LocalEmbeddings,
    LocalEmbeddingSettings,
    RemoteEmbeddings,
    create_embeddings,
)
from herta_agent.rag.errors import RagError


class LocalEmbeddingTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, root):
        path = Path(root)
        for name in ("config.json", "tokenizer.json", "model.safetensors"):
            (path / name).write_bytes(b"{}" if name.endswith(".json") else b"weights")
        return path

    async def test_explicit_remote_config_beats_machine_cache(self):
        env = {
            "HERTA_EMBEDDING_BASE_URL": "https://embedding.invalid/v1",
            "HERTA_EMBEDDING_MODEL": "remote",
            "HERTA_EMBEDDING_API_KEY": "fixture",
        }
        client = MagicMock(spec=httpx.AsyncClient)
        with patch.dict(os.environ, env, clear=True):
            self.assertIsInstance(create_embeddings(client), RemoteEmbeddings)

    async def test_explicit_local_path_and_incomplete_path_fail_without_network(self):
        client = MagicMock(spec=httpx.AsyncClient)
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root)
            env = {"HERTA_LOCAL_EMBEDDING_MODEL": str(path)}
            with patch.dict(os.environ, env, clear=True):
                adapter = create_embeddings(client)
                self.assertIsInstance(adapter, LocalEmbeddings)
                self.assertEqual(adapter.settings.model_path, path.resolve())
            (path / "model.safetensors").unlink()
            with patch.dict(os.environ, env, clear=True), self.assertRaises(RagError) as caught:
                create_embeddings(client)
            self.assertEqual(caught.exception.code, "embedding_config")

    async def test_fingerprint_tracks_weights_and_query_encoding(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root)
            first = LocalEmbeddingSettings(model_path=path)
            changed = LocalEmbeddingSettings(model_path=path, query_prefix="query: ")
            self.assertNotEqual(first.fingerprint, changed.fingerprint)
            original = first.fingerprint
            (path / "model.safetensors").write_bytes(b"changed-weights")
            self.assertNotEqual(original, first.fingerprint)

    async def test_query_instruction_and_validation(self):
        with tempfile.TemporaryDirectory() as root:
            adapter = LocalEmbeddings(LocalEmbeddingSettings(model_path=self.fixture(root)))
            with patch.object(adapter, "_encode", return_value=[[1.0, 0.0]]) as encode:
                self.assertEqual(await adapter.embed_query("人物关系"), [1.0, 0.0])
                encode.assert_called_once_with(["为这个句子生成表示以用于检索相关文章：人物关系"])
            with self.assertRaises(RagError):
                await adapter.embed_query("  ")
            with self.assertRaises(RagError):
                await adapter.embed_documents([123])

    async def test_blank_desktop_remote_fields_allow_local_auto(self):
        client = MagicMock(spec=httpx.AsyncClient)
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root)
            env = {
                "HERTA_LOCAL_EMBEDDING_MODEL": str(path),
                "HERTA_EMBEDDING_BASE_URL": "",
                "HERTA_EMBEDDING_MODEL": "",
            }
            with patch.dict(os.environ, env, clear=True):
                self.assertIsInstance(create_embeddings(client), LocalEmbeddings)
