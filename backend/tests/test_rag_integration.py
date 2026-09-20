"""Full adapters and CLI composition, with HTTP transport replaced at the network boundary."""

import contextlib
import io
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx

from herta_agent.__main__ import main
from herta_agent.rag.embeddings import EmbeddingSettings
from herta_agent.rag.ingest import load_corpus
from herta_agent.rag.store import publish_index

ROOT = Path(__file__).resolve().parents[2]


class RagIntegrationTests(unittest.TestCase):
    def test_independent_services_full_tool_loop_and_persona(self):
        env = {
            "HERTA_BASE_URL": "https://chat.invalid/v1",
            "HERTA_MODEL": "chat-model",
            "HERTA_API_KEY": uuid.uuid4().hex,
            "HERTA_EMBEDDING_BASE_URL": "https://embedding.invalid/v1",
            "HERTA_EMBEDDING_MODEL": "embedding-model",
            "HERTA_EMBEDDING_API_KEY": uuid.uuid4().hex,
        }
        requests = []
        bodies = []

        def handler(request):
            requests.append(request)
            payload = json.loads(request.content)
            if request.url.host == "embedding.invalid":
                self.assertEqual(payload["model"], "embedding-model")
                self.assertEqual(payload["input"], ["黑塔身份"])
                self.assertEqual(
                    request.headers["authorization"], "Bearer " + env["HERTA_EMBEDDING_API_KEY"]
                )
                return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]})
            self.assertEqual(request.headers["authorization"], "Bearer " + env["HERTA_API_KEY"])
            self.assertEqual(payload["model"], "chat-model")
            bodies.append(payload)
            if len(bodies) == 1:
                response = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "search",
                            "type": "function",
                            "function": {
                                "name": "search_knowledge",
                                "arguments": '{"query":"黑塔身份"}',
                            },
                        }
                    ],
                }
                finish = "tool_calls"
            else:
                result = json.loads(payload["messages"][-1]["content"])
                self.assertTrue(result["ok"])
                self.assertEqual(result["data"]["chunks"][0]["unit_id"], "K01")
                chunk_id = result["data"]["chunks"][0]["id"]
                response = {"role": "assistant", "content": f"第 83 席 [{chunk_id}]"}
                finish = "stop"
            return httpx.Response(
                200, json={"choices": [{"message": response, "finish_reason": finish}]}
            )

        original_client = httpx.AsyncClient

        def client_factory(**kwargs):
            return original_client(transport=httpx.MockTransport(handler), **kwargs)

        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, env, clear=True):
            corpus = load_corpus(ROOT / "knowledge")
            settings = EmbeddingSettings.from_env()
            publish_index(
                Path(temporary),
                corpus,
                [[1.0, 0.0]] + [[0.0, 1.0]] * 19,
                settings.fingerprint,
                settings.model,
            )
            stdout = io.StringIO()
            with (
                patch("httpx.AsyncClient", side_effect=client_factory),
                patch(
                    "sys.argv",
                    [
                        "herta_agent",
                        "--provider",
                        "openai",
                        "--rag-index",
                        temporary,
                        "--message",
                        "黑塔是谁？",
                    ],
                ),
                contextlib.redirect_stdout(stdout),
            ):
                main()
            self.assertIn("[steps=2]", stdout.getvalue())
            self.assertEqual(len(requests), 3)
            system = (ROOT / "persona/soul.md").read_bytes().decode("utf-8-sig")
            for body in bodies:
                self.assertEqual(body["messages"][0], {"role": "system", "content": system})
            self.assertIn("search_knowledge", [t["function"]["name"] for t in bodies[0]["tools"]])

    def test_unavailable_rag_is_explicit_but_does_not_block_ordinary_chat(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "你好。"},
                        }
                    ]
                },
            )

        original_client = httpx.AsyncClient
        env = {
            "HERTA_BASE_URL": "https://chat.invalid/v1",
            "HERTA_MODEL": "chat",
            "HERTA_API_KEY": uuid.uuid4().hex,
        }
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, env, clear=True),
            patch(
                "httpx.AsyncClient",
                side_effect=lambda **kw: original_client(
                    transport=httpx.MockTransport(handler), **kw
                ),
            ),
            patch("sys.argv", ["herta_agent", "--provider", "openai", "--message", "你好"]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            main()
        self.assertIn("embedding_config", stderr.getvalue())
        self.assertIn("Assistant: 你好", stdout.getvalue())
        self.assertEqual(len(requests), 1)
