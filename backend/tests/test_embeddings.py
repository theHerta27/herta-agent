import asyncio
import importlib.util
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

from herta_agent.rag.errors import RagError


class EmbeddingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("herta_agent.rag.embeddings"), "embedding adapter must exist"
        )
        from herta_agent.rag.embeddings import EmbeddingSettings, RemoteEmbeddings

        self.Settings = EmbeddingSettings
        self.Remote = RemoteEmbeddings
        self.secret = uuid4().hex
        self.env = {
            "HERTA_EMBEDDING_BASE_URL": "https://embedding.invalid/v1",
            "HERTA_EMBEDDING_MODEL": "embedding-test",
            "HERTA_EMBEDDING_API_KEY": self.secret,
        }

    def settings(self, **changes):
        with patch.dict(os.environ, self.env | changes, clear=True):
            return self.Settings.from_env()

    def test_config_is_independent_secret_free_and_fingerprinted(self):
        settings = self.settings()
        self.assertNotIn(self.secret, repr(settings))
        self.assertNotIn("api_key", settings.model_dump())
        self.assertNotIn(self.secret, settings.model_dump_json())
        changed_key = self.settings(HERTA_EMBEDDING_API_KEY=uuid4().hex)
        self.assertEqual(settings.fingerprint, changed_key.fingerprint)
        for name, value in [
            ("MODEL", "another"),
            ("BASE_URL", "https://other.invalid"),
            ("DOCUMENT_PREFIX", "doc: "),
            ("QUERY_PREFIX", "query: "),
            ("MAX_INPUT_CHARS", "20"),
        ]:
            self.assertNotEqual(
                settings.fingerprint,
                self.settings(**{"HERTA_EMBEDDING_" + name: value}).fingerprint,
            )

    def test_invalid_config_is_sanitized(self):
        invalid = [
            {"HERTA_EMBEDDING_API_KEY": ""},
            {"HERTA_EMBEDDING_MODEL": ""},
            {"HERTA_EMBEDDING_TIMEOUT": "nan"},
            {"HERTA_EMBEDDING_BATCH_SIZE": "0"},
        ]
        invalid.extend(
            {"HERTA_EMBEDDING_BASE_URL": u}
            for u in [
                "file:///tmp/model",
                "https://user:" + self.secret + "@example.invalid",
                "https://example.invalid?q=" + self.secret,
                "https://example.invalid#fragment",
            ]
        )
        for changes in invalid:
            with self.assertRaises(RagError) as caught:
                self.settings(**changes)
            self.assertEqual(caught.exception.code, "embedding_config")
            self.assertNotIn(self.secret, str(caught.exception))
        with patch.dict(os.environ, {"OPENAI_API_KEY": self.secret}, clear=True):
            with self.assertRaises(RagError):
                self.Settings.from_env()

    async def test_batches_restore_order_and_use_separate_prefixes(self):
        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(str(request.url), "https://embedding.invalid/v1/embeddings")
            self.assertEqual(request.headers["authorization"], "Bearer " + self.secret)
            self.assertEqual(body["encoding_format"], "float")
            self.assertEqual(request.extensions["timeout"]["read"], 7.0)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": i, "embedding": [i + 1, 2]}
                        for i in reversed(range(len(body["input"])))
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = self.Remote(
                self.settings(
                    HERTA_EMBEDDING_BATCH_SIZE="2",
                    HERTA_EMBEDDING_TIMEOUT="7",
                    HERTA_EMBEDDING_DOCUMENT_PREFIX="D: ",
                    HERTA_EMBEDDING_QUERY_PREFIX="Q: ",
                ),
                client,
            )
            self.assertEqual(
                await adapter.embed_documents(["a", "b", "c"]), [[1.0, 2.0], [2.0, 2.0], [1.0, 2.0]]
            )
            self.assertEqual(await adapter.embed_query("a"), [1.0, 2.0])
            self.assertFalse(client.is_closed)
            self.assertEqual(adapter.model, "embedding-test")
        self.assertEqual([r["input"] for r in requests], [["D: a", "D: b"], ["D: c"], ["Q: a"]])

    async def test_inputs_rejected_before_any_request(self):
        def handler(request):
            self.fail("invalid input was transmitted")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = self.Remote(
                self.settings(
                    HERTA_EMBEDDING_MAX_INPUT_CHARS="5", HERTA_EMBEDDING_QUERY_PREFIX="Q: "
                ),
                client,
            )
            self.assertEqual(await adapter.embed_documents([]), [])
            for query in ["", "  ", "abc", 3]:
                with self.assertRaises(RagError) as caught:
                    await adapter.embed_query(query)
                self.assertEqual(caught.exception.code, "embedding_input")
            with self.assertRaises(RagError):
                await adapter.embed_documents(["ok", "too long"])

    async def test_invalid_response_shapes_and_vectors(self):
        invalid = [
            None,
            {},
            {"data": []},
            {"data": [{"index": True, "embedding": [1]}]},
            {"data": [{"index": 1, "embedding": [1]}]},
            *(
                {"data": [{"index": 0, "embedding": v}]}
                for v in [[], [0, 0], [True], ["1"], [None], [float("inf")], [float("nan")]]
            ),
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda r, payload=payload: httpx.Response(200, content=json.dumps(payload))
                    )
                ) as client:
                    with self.assertRaises(RagError) as caught:
                        await self.Remote(self.settings(), client).embed_query("q")
                    self.assertEqual(caught.exception.code, "embedding_response")

    async def test_duplicate_indices_and_cross_batch_dimensions_rejected(self):
        for rows in [
            [{"index": 0, "embedding": [1]}, {"index": 0, "embedding": [2]}],
            [{"index": 0, "embedding": [1]}, {"index": 1, "embedding": [1, 2]}],
        ]:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda r, rows=rows: httpx.Response(200, json={"data": rows})
                )
            ) as client:
                with self.assertRaises(RagError):
                    await self.Remote(self.settings(), client).embed_documents(["a", "b"])
        sizes = iter([1, 2])
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, json={"data": [{"index": 0, "embedding": [1] * next(sizes)}]}
                )
            )
        ) as client:
            with self.assertRaises(RagError):
                await self.Remote(
                    self.settings(HERTA_EMBEDDING_BATCH_SIZE="1"), client
                ).embed_documents(["a", "b"])

    async def test_errors_are_sanitized_and_never_retried(self):
        for outcome, code in [
            (httpx.Response(401, text=self.secret), "embedding_http"),
            (httpx.Response(302, headers={"location": "https://other.invalid"}), "embedding_http"),
            (httpx.Response(200, text=self.secret), "embedding_response"),
            (httpx.ReadTimeout(self.secret), "embedding_timeout"),
            (httpx.ConnectError(self.secret), "embedding_http"),
        ]:
            calls = []

            def handler(request, calls=calls, outcome=outcome):
                calls.append(request)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), follow_redirects=True
            ) as client:
                with self.assertRaises(RagError) as caught:
                    await self.Remote(self.settings(), client).embed_query("q")
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(self.secret, str(caught.exception))
                self.assertEqual(len(calls), 1)

    async def test_cancellation_propagates(self):
        def handler(request):
            raise asyncio.CancelledError()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(asyncio.CancelledError):
                await self.Remote(self.settings(), client).embed_query("q")

    async def test_total_timeout_cancels_blocked_http_operation(self):
        cancelled = asyncio.Event()

        async def handler(request):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = self.Remote(self.settings(HERTA_EMBEDDING_TIMEOUT="0.01"), client)
            with self.assertRaises(RagError) as caught:
                await asyncio.wait_for(adapter.embed_query("q"), timeout=0.5)
            self.assertEqual(caught.exception.code, "embedding_timeout")
            self.assertTrue(cancelled.is_set())
