"""Explicit legacy RAG composition; only the HTTP transport is replaced."""

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx

from herta_agent.config import ProviderSettings
from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
from herta_agent.persona import PersonaContextBuilder
from herta_agent.rag.embeddings import EmbeddingSettings
from herta_agent.rag.errors import RagError
from herta_agent.rag.ingest import load_corpus
from herta_agent.rag.retriever import SearchSettings
from herta_agent.rag.service import load_retriever
from herta_agent.rag.store import publish_index
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.session import Session
from herta_agent.tools.registry import ToolRegistry
from herta_agent.tools.search_knowledge import search_knowledge_spec

ROOT = Path(__file__).resolve().parents[2]


class RagIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_independent_services_full_tool_loop_and_persona(self):
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
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                registry = ToolRegistry()
                registry.register(
                    search_knowledge_spec(
                        load_retriever(
                            client, ROOT / "knowledge", Path(temporary), SearchSettings()
                        )
                    )
                )
                agent = Agent(
                    OpenAICompatibleProvider(ProviderSettings.from_env(), client),
                    registry=registry,
                    context_builder=PersonaContextBuilder(ROOT / "persona/soul.md"),
                )
                result = await agent.run(Session(), "黑塔是谁？")
            self.assertEqual(result.steps, 2)
            self.assertEqual(len(requests), 3)
            system = (ROOT / "persona/soul.md").read_bytes().decode("utf-8-sig")
            for body in bodies:
                self.assertEqual(body["messages"][0], {"role": "system", "content": system})
            self.assertIn("search_knowledge", [t["function"]["name"] for t in bodies[0]["tools"]])

    async def test_explicit_unavailable_rag_does_not_block_ordinary_chat(self):
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

        env = {
            "HERTA_BASE_URL": "https://chat.invalid/v1",
            "HERTA_MODEL": "chat",
            "HERTA_API_KEY": uuid.uuid4().hex,
            "HERTA_EMBEDDING_PROVIDER": "remote",
        }
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, env, clear=True):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(RagError) as caught:
                    load_retriever(client, ROOT / "knowledge", Path(temporary), SearchSettings())
                self.assertEqual(caught.exception.code, "embedding_config")
                registry = ToolRegistry()
                registry.register(search_knowledge_spec(unavailable=caught.exception))
                agent = Agent(
                    OpenAICompatibleProvider(ProviderSettings.from_env(), client), registry=registry
                )
                result = await agent.run(Session(), "你好")
        self.assertEqual(result.reply, "你好。")
        self.assertEqual(len(requests), 1)
