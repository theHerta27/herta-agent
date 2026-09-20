import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from herta_agent.rag.errors import RagError
from herta_agent.rag.ingest import load_corpus
from herta_agent.rag.store import load_index, publish_index


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.corpus = load_corpus(Path(__file__).resolve().parents[2] / "knowledge")
        self.vectors = [[3.0, 4.0] for _ in self.corpus.chunks]

    def publish(self):
        return publish_index(self.root, self.corpus, self.vectors, "f" * 64, "test-model")

    def test_roundtrip_and_normalization_snapshot(self):
        first = self.publish()
        self.assertTrue(np.allclose(first.vectors[0], [0.6, 0.8]))
        loaded = load_index(self.root, self.corpus, "f" * 64)
        self.assertEqual(loaded.chunks, self.corpus.chunks)
        self.assertFalse(loaded.vectors.flags.writeable)
        second = self.publish()
        self.assertNotEqual(first.index_id, second.index_id)
        self.assertTrue(np.allclose(first.vectors, second.vectors))
        self.assertEqual(load_index(self.root, self.corpus, "f" * 64).index_id, second.index_id)

    def test_failed_publication_preserves_pointer(self):
        first = self.publish()
        with patch("herta_agent.rag.store.os.replace", side_effect=OSError("busy")):
            with self.assertRaises(RagError):
                self.publish()
        self.assertEqual(load_index(self.root, self.corpus, "f" * 64).index_id, first.index_id)

    def test_invalid_vectors(self):
        for value in (
            [],
            [[0.0, 0.0]] * 20,
            [[float("nan"), 1.0]] * 20,
            [[1.0, 2.0]] * 19,
            [[1.0], [1.0, 2.0]],
            [[True, 1.0]] * 20,
        ):
            with self.subTest(value=repr(value)[:50]), self.assertRaises(RagError):
                publish_index(self.root, self.corpus, value, "f" * 64, "model")
        self.assertFalse((self.root / "current.json").exists())

    def test_mismatch_corruption_and_pointer_traversal(self):
        snapshot = self.publish()
        with self.assertRaises(RagError) as raised:
            load_index(self.root, self.corpus, "e" * 64)
        self.assertEqual(raised.exception.code, "index_mismatch")
        directory = self.root / snapshot.index_id
        (directory / "chunks.jsonl").write_text("{}", encoding="utf-8")
        with self.assertRaises(RagError) as raised:
            load_index(self.root, self.corpus, "f" * 64)
        self.assertEqual(raised.exception.code, "index_invalid")
        (self.root / "current.json").write_text(json.dumps({"index_id": "../outside"}))
        with self.assertRaises(RagError):
            load_index(self.root, self.corpus, "f" * 64)

    def test_missing_index_is_distinct(self):
        with self.assertRaises(RagError) as raised:
            load_index(self.root, self.corpus, "f" * 64)
        self.assertEqual(raised.exception.code, "index_missing")

    def test_npz_and_bool_arrays_are_rejected(self):
        from herta_agent.rag.ingest import digest
        from herta_agent.rag.store import normalized_vectors

        with self.assertRaises(RagError):
            normalized_vectors(np.array([[True, False]]), count=1)
        snapshot = self.publish()
        directory = self.root / snapshot.index_id
        path = directory / "vectors.npy"
        with path.open("wb") as stream:
            np.savez(stream, vectors=snapshot.vectors)
        manifest = snapshot.manifest.model_dump()
        manifest["vectors_sha256"] = digest(path.read_bytes())
        (directory / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(RagError) as raised:
            load_index(self.root, self.corpus, "f" * 64)
        self.assertEqual(raised.exception.code, "index_invalid")
