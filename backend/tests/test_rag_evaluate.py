import json
import tempfile
import unittest
from pathlib import Path

from test_tool_loop import ScriptedProvider

from herta_agent.rag.errors import RagError
from herta_agent.rag.evaluate import evaluate_chat, evaluate_retrieval, load_questions
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import ProviderError
from herta_agent.runtime.messages import Message, ToolCall
from herta_agent.tools.registry import ToolRegistry
from herta_agent.tools.search_knowledge import search_knowledge_spec

PROJECT = Path(__file__).resolve().parents[2]
CHUNK = "K01-0123456789abcdef"
OTHER = "K02-0123456789abcdef"


def question(**overrides):
    return dict(
        id="Q01",
        split="dev",
        kind="answerable",
        question="黑塔是谁？",
        should_retrieve=True,
        required_evidence=["K01"],
        supporting_context=[],
        expected="据证回答",
        forbidden=["编造"],
        **overrides,
    )


def load_fixture(rows):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "questions.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        return load_questions(path, {"K01", "K02"})


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    def test_real_questions_and_strict_contract(self):
        rows = load_questions(
            PROJECT / "evals/rag/questions.jsonl", {f"K{i:02}" for i in range(1, 21)}
        )
        self.assertEqual(len(rows), 28)
        self.assertEqual(sum(q.split == "dev" for q in rows), 17)
        bad_rows = []
        for changes in (
            {"extra": 1},
            {"should_retrieve": "true"},
            {"required_evidence": []},
            {"required_evidence": ["K99"]},
            {"supporting_context": ["K99"]},
            {"split": "train"},
            {"question": " "},
            {"should_retrieve": False},
            {"kind": "no_retrieval"},
        ):
            row = question()
            row.update(changes)
            bad_rows.append([row])
        bad_rows.append([question(), question()])
        for rows in bad_rows:
            with self.subTest(rows=rows), self.assertRaises(RagError) as caught:
                load_fixture(rows)
            self.assertEqual(caught.exception.code, "invalid_questions")

    async def test_retrieval_unit_dedup_raw_filtered_cross_and_skipped_routing(self):
        rows = [question()]
        cross = question()
        cross.update(id="Q02", kind="cross_section", required_evidence=["K01", "K02"])
        insufficient = question()
        insufficient.update(
            id="Q03", kind="insufficient", required_evidence=[], supporting_context=["K01"]
        )
        no_retrieval = question()
        no_retrieval.update(
            id="Q04", kind="no_retrieval", should_retrieve=False, required_evidence=[]
        )
        rows.extend([cross, insufficient, no_retrieval])

        class Retriever:
            calls = 0

            async def inspect(self, query):
                self.calls += 1
                return {
                    "query": query,
                    "index_id": "index",
                    "method": "exact_cosine",
                    "settings": {"k": 3, "min_score": 0.4, "max_chars": 1000},
                    "chunks": [
                        {"id": CHUNK, "unit_id": "K01", "text": "甲"},
                        {"id": "duplicate", "unit_id": "K01", "text": "乙"},
                    ],
                    "candidates": [
                        {"id": CHUNK, "unit_id": "K01", "reason": "selected"},
                        {"id": "duplicate", "unit_id": "K01", "reason": "selected"},
                        {"id": OTHER, "unit_id": "K02", "reason": "budget"},
                    ],
                    "reason": "evidence_returned",
                }

        retriever = Retriever()
        report = await evaluate_retrieval(retriever, load_fixture(rows), split="all")
        self.assertEqual(retriever.calls, 3)
        self.assertEqual(report["summary"]["required_unit_count"], 3)
        self.assertEqual(report["summary"]["filtered_required_unit_hits"], 2)
        self.assertEqual(report["summary"]["raw_top_k_required_unit_hits"], 3)
        self.assertEqual(report["summary"]["cross_section_complete"], 0)
        self.assertEqual(report["questions"][1]["missing_required"], ["K02"])
        self.assertEqual(report["questions"][1]["returned_text_chars"], 2)
        self.assertEqual(report["questions"][2]["answerability"], "not_measured")
        self.assertEqual(report["questions"][3]["status"], "skipped_no_retrieval")
        self.assertEqual(report["questions"][3]["routing"], "not_measured")
        self.assertEqual(
            report["questions"][1]["diagnostics"]["candidates"][-1]["reason"], "budget"
        )
        self.assertEqual(report["questions"][0]["semantic_judgment"], "pending_manual_review")

    async def test_chat_only_delivered_citations_fresh_sessions_and_pending_judgment(self):
        class Retriever:
            async def search(self, query):
                return {"chunks": [{"id": CHUNK, "unit_id": "K01", "text": "事实"}]}

        registry = ToolRegistry()
        registry.register(search_knowledge_spec(Retriever()))
        provider = ScriptedProvider(
            Message(
                role="assistant",
                tool_calls=(
                    ToolCall(
                        id="search", name="search_knowledge", arguments='{"query":"改写查询"}'
                    ),
                ),
            ),
            Message(role="assistant", content=f"答案 [{CHUNK}] [{OTHER}]"),
            Message(role="assistant", content=f"上轮引用 [{CHUNK}]"),
        )
        second = question()
        second.update(id="Q02", kind="no_retrieval", should_retrieve=False, required_evidence=[])
        report = await evaluate_chat(
            Agent(provider, registry=registry), load_fixture([question(), second])
        )
        first, second = report["questions"]
        self.assertTrue(first["routing_correct"])
        self.assertEqual(first["actual_queries"], ["改写查询"])
        self.assertEqual(first["delivered_chunk_ids"], [CHUNK])
        self.assertEqual(first["invalid_citations"], [OTHER])
        self.assertEqual(second["invalid_citations"], [CHUNK])
        self.assertTrue(second["routing_correct"])
        self.assertEqual(first["groundedness"], "pending_manual_review")
        self.assertEqual(first["unknown_handling"], "pending_manual_review")
        self.assertEqual(first["expected_judgment"], "pending_manual_review")
        self.assertEqual(sum(m.role == "user" for m in provider.requests[-1][0]), 1)

    async def test_failed_run_never_counts_correct_and_sanitizes_error(self):
        class FailedProvider:
            async def complete(self, messages, *, tools=()):
                raise ProviderError("private-key HTTP body")

        row = question()
        row.update(kind="no_retrieval", should_retrieve=False, required_evidence=[])
        report = await evaluate_chat(Agent(FailedProvider()), load_fixture([row]))
        result = report["questions"][0]
        self.assertEqual(result["status"], "run_failed")
        self.assertFalse(result["routing_correct"])
        self.assertEqual(result["error_code"], "agent_error")
        self.assertNotIn("private-key", json.dumps(report))

    async def test_unexpected_tool_reported_and_retrieval_error_sanitized(self):
        provider = ScriptedProvider(
            Message(role="assistant", tool_calls=(ToolCall(id="x", name="other", arguments="{}"),)),
            Message(role="assistant", content="完成"),
        )
        report = await evaluate_chat(Agent(provider), load_fixture([question()]))
        self.assertEqual(report["questions"][0]["unexpected_tools"], ["other"])
        self.assertFalse(report["questions"][0]["routing_correct"])

        class FailedRetriever:
            async def inspect(self, query):
                raise RagError("embedding_failed", "private-key")

        report = await evaluate_retrieval(FailedRetriever(), load_fixture([question()]))
        self.assertEqual(report["questions"][0]["error_code"], "retrieval_error")
        self.assertNotIn("private-key", json.dumps(report))
