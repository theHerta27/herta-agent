import asyncio
import tempfile
import unittest
from pathlib import Path

from herta_agent.rag.errors import RagError
from herta_agent.rag.ingest import load_corpus
from herta_agent.rag.retriever import Retriever, SearchSettings
from herta_agent.rag.store import publish_index


class FakeEmbedding:
    fingerprint = "f" * 64
    model = "fixture"

    async def embed_query(self, text):
        return [10.0, 0.0]


class RetrieverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        corpus = load_corpus(Path(__file__).resolve().parents[2] / "knowledge")
        vectors = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]] + [[-1.0, 0.0]] * 17
        self.index = publish_index(Path(tmp.name), corpus, vectors, "f" * 64, "fixture")

    async def test_exact_ranking_score_threshold_and_diagnostics(self):
        retriever = Retriever(self.index, FakeEmbedding(), SearchSettings(k=2, min_score=0.1))
        report = await retriever.inspect("不共享词面的查询")
        self.assertEqual([c["unit_id"] for c in report["chunks"]], ["K01", "K03"])
        self.assertAlmostEqual(report["chunks"][0]["score"], 1.0)
        self.assertAlmostEqual(report["chunks"][1]["score"], 2**-0.5, places=6)
        self.assertEqual(len(report["candidates"]), 20)
        self.assertEqual(report["candidates"][2]["reason"], "below_threshold")
        self.assertNotIn("candidates", await retriever.search("query"))

    async def test_empty_budget_ties_and_validation(self):
        retriever = Retriever(self.index, FakeEmbedding(), SearchSettings(max_chars=1))
        result = await retriever.search("query")
        self.assertEqual(result["reason"], "no_relevant_evidence")
        self.assertEqual(result["chunks"], [])
        full = Retriever(self.index, FakeEmbedding(), SearchSettings(k=20, min_score=-1.0))
        candidates = (await full.inspect("query"))["candidates"]
        ties = [c["id"] for c in candidates if c["score"] == -1.0]
        self.assertEqual(ties, sorted(ties))
        with self.assertRaises(RagError):
            await full.search(" ")
        with self.assertRaises(RagError):
            await full.search("字" * 1001)
        for invalid in ({"k": 0}, {"k": True}, {"min_score": float("nan")}, {"max_chars": 0}):
            with self.assertRaises(ValueError):
                SearchSettings(**invalid)

    async def test_mismatch_dimension_and_cancellation(self):
        class Wrong(FakeEmbedding):
            async def embed_query(self, text):
                return [1.0, 0.0, 0.0]

        with self.assertRaises(RagError):
            await Retriever(self.index, Wrong()).search("query")
        entered = asyncio.Event()

        class Slow(FakeEmbedding):
            async def embed_query(self, text):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(Retriever(self.index, Slow()).search("query"))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_overlapping_same_unit_is_dropped(self):
        from dataclasses import replace

        first = self.index.chunks[0]
        duplicate = first.model_copy(update={"id": "K01-" + "a" * 16})
        index = replace(self.index, chunks=(first, duplicate) + self.index.chunks[2:])
        # Give both overlapping chunks the top score.
        vectors = index.vectors.copy()
        vectors[1] = vectors[0]
        index = replace(index, vectors=vectors)
        report = await Retriever(index, FakeEmbedding()).inspect("query")
        self.assertEqual(sum(c["reason"] == "overlap" for c in report["candidates"]), 1)
