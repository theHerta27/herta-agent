"""Separate engineering observations from manual semantic evaluation."""

import json
import re
from pathlib import Path
from time import perf_counter
from typing import Annotated, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from herta_agent.rag.errors import RagError
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import AgentError
from herta_agent.runtime.session import Session

Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
UnitId = Annotated[str, Field(pattern=r"^K\d{2}$")]
PENDING = "pending_manual_review"
CITATION = re.compile(r"\[(K\d{2}[^\]\r\n]*)\]")


class Question(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    id: str = Field(pattern=r"^Q\d{2}$")
    split: Literal["dev", "check"]
    kind: Literal["answerable", "cross_section", "insufficient", "no_retrieval"]
    question: Nonempty
    should_retrieve: bool
    required_evidence: list[UnitId]
    supporting_context: list[UnitId]
    expected: Nonempty
    forbidden: list[Nonempty]

    @model_validator(mode="after")
    def consistent(self) -> "Question":
        if self.should_retrieve != (self.kind != "no_retrieval"):
            raise ValueError("Retrieval expectation conflicts with question kind")
        if self.kind in {"answerable", "cross_section"} and not self.required_evidence:
            raise ValueError("Answerable questions require evidence")
        if self.kind in {"insufficient", "no_retrieval"} and self.required_evidence:
            raise ValueError("Unanswerable questions cannot require answer evidence")
        if self.kind == "cross_section" and len(set(self.required_evidence)) < 2:
            raise ValueError("Cross-section questions require multiple units")
        for ids in (self.required_evidence, self.supporting_context):
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate evidence units")
        return self


def load_questions(path: Path, unit_ids: set[str]) -> tuple[Question, ...]:
    """Load the versioned question schema, validating references against the corpus."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        questions = tuple(Question.model_validate_json(line) for line in lines if line.strip())
        if not questions or len({q.id for q in questions}) != len(questions):
            raise ValueError("Empty or duplicate questions")
        for question in questions:
            if not set(question.required_evidence + question.supporting_context) <= unit_ids:
                raise ValueError("Unknown evidence unit")
        return questions
    except (OSError, UnicodeError, ValidationError, ValueError):
        raise RagError("invalid_questions", "评测题集格式或证据引用无效。") from None


class InspectRetriever(Protocol):
    async def inspect(self, query: str) -> dict: ...


def _selected(questions: tuple[Question, ...], split: str) -> tuple[Question, ...]:
    if split not in {"dev", "check", "all"}:
        raise RagError("invalid_split", "评测划分必须为 dev、check 或 all。")
    return tuple(q for q in questions if split == "all" or q.split == split)


def _base(question: Question) -> dict:
    return {**question.model_dump(), "semantic_judgment": PENDING}


def _report(mode: str, split: str, rows: list[dict], summary: dict) -> dict:
    return {
        "mode": mode,
        "split": split,
        "status": "engineering_observations",
        "semantic_judgment": PENDING,
        "limitations": [
            "引用存在或证据覆盖不代表语义正确；答案必须人工核对。",
            "固定向量和脚本模型仅验证工程行为，不是实际模型质量成绩。",
        ],
        "questions": rows,
        "summary": summary,
    }


async def evaluate_retrieval(
    retriever: InspectRetriever, questions: tuple[Question, ...], split: str = "dev"
) -> dict:
    """Query original question text; measure unique required units, never answerability."""
    rows = []
    required_count = filtered_hits = raw_hits = cross_count = cross_complete = 0
    for question in _selected(questions, split):
        started = perf_counter()
        required = set(question.required_evidence)
        required_count += len(required)
        cross_count += question.kind == "cross_section"
        row = {**_base(question), "routing": "not_measured", "answerability": "not_measured"}
        if not question.should_retrieve:
            row["status"] = "skipped_no_retrieval"
            row["elapsed_seconds"] = perf_counter() - started
            rows.append(row)
            continue
        try:
            result = await retriever.inspect(question.question)
        except RagError:
            row.update(
                status="retrieval_failed",
                error_code="retrieval_error",
                missing_required=sorted(required),
            )
            row["elapsed_seconds"] = perf_counter() - started
            rows.append(row)
            continue
        chunks = result["chunks"]
        candidates = result["candidates"]
        settings = {key: result["settings"][key] for key in ("k", "min_score", "max_chars")}
        raw_units = {chunk["unit_id"] for chunk in candidates[: settings["k"]]}
        filtered_units = {chunk["unit_id"] for chunk in chunks}
        hit = len(required & filtered_units)
        raw_hit = len(required & raw_units)
        filtered_hits += hit
        raw_hits += raw_hit
        complete = required <= filtered_units if required else None
        if question.kind == "cross_section" and complete:
            cross_complete += 1
        row.update(
            status="observed",
            elapsed_seconds=perf_counter() - started,
            raw_top_k_units=sorted(raw_units),
            returned_units=sorted(filtered_units),
            raw_top_k_required_hits=raw_hit,
            filtered_required_hits=hit,
            raw_top_k_recall=raw_hit / len(required) if required else None,
            filtered_recall=hit / len(required) if required else None,
            missing_required=sorted(required - filtered_units),
            all_required_present=complete,
            returned_text_chars=sum(len(chunk["text"]) for chunk in chunks),
            diagnostics={
                "query": result["query"],
                "index_id": result["index_id"],
                "method": result["method"],
                "settings": settings,
                "chunks": chunks,
                "candidates": candidates,
                "reason": result["reason"],
            },
        )
        rows.append(row)
    return _report(
        "direct_retrieval",
        split,
        rows,
        {
            "question_count": len(rows),
            "required_unit_count": required_count,
            "filtered_required_unit_hits": filtered_hits,
            "raw_top_k_required_unit_hits": raw_hits,
            "filtered_recall": filtered_hits / required_count if required_count else None,
            "raw_top_k_recall": raw_hits / required_count if required_count else None,
            "cross_section_count": cross_count,
            "cross_section_complete": cross_complete,
            "routing": "not_measured",
            "answerability": "not_measured",
        },
    )


async def evaluate_chat(agent: Agent, questions: tuple[Question, ...], split: str = "all") -> dict:
    """Run ordinary Agent turns in fresh sessions and inspect actual tool feedback."""
    rows = []
    for question in _selected(questions, split):
        started = perf_counter()
        session = Session()
        row = {
            **_base(question),
            "status": "observed",
            "groundedness": PENDING,
            "unknown_handling": PENDING,
            "expected_judgment": PENDING,
        }
        answer = None
        try:
            result = await agent.run(session, question.question)
            answer = result.reply
        except AgentError:
            row.update(status="run_failed", error_code="agent_error")
        searches = {}
        unexpected = []
        for message in session.history:
            for call in message.tool_calls:
                if call.name != "search_knowledge":
                    unexpected.append(call.name)
                    continue
                try:
                    arguments = json.loads(call.arguments)
                except (ValueError, TypeError):
                    arguments = None
                searches[call.id] = {
                    "call_id": call.id,
                    "query": arguments.get("query") if isinstance(arguments, dict) else None,
                    "result": None,
                }
        delivered = set()
        for message in session.history:
            if message.role != "tool" or message.tool_call_id not in searches:
                continue
            try:
                envelope = json.loads(message.content)
            except (ValueError, TypeError):
                continue
            searches[message.tool_call_id]["result"] = envelope
            if isinstance(envelope, dict) and envelope.get("ok") is True:
                data = envelope.get("data")
                if isinstance(data, dict) and isinstance(data.get("chunks"), list):
                    for chunk in data["chunks"]:
                        if isinstance(chunk, dict) and isinstance(chunk.get("id"), str):
                            delivered.add(chunk["id"])
        citations = sorted(set(CITATION.findall(answer or "")))
        routing = bool(searches) == question.should_retrieve
        row.update(
            elapsed_seconds=perf_counter() - started,
            tool_calls=list(searches.values()),
            actual_queries=[search["query"] for search in searches.values()],
            delivered_chunk_ids=sorted(delivered),
            citations=citations,
            invalid_citations=sorted(set(citations) - delivered),
            citation_provenance_valid=not (set(citations) - delivered),
            citation_missing=bool(delivered) and not citations,
            context_hash=session.context_hash,
            unexpected_tools=unexpected,
            routing_correct=row["status"] == "observed" and routing and not unexpected,
            answer=answer,
        )
        rows.append(row)
    return _report(
        "formal_chat",
        split,
        rows,
        {
            "question_count": len(rows),
            "completed_runs": sum(row["status"] == "observed" for row in rows),
            "routing_correct_count": sum(row["routing_correct"] for row in rows),
            "invalid_citation_count": sum(len(row["invalid_citations"]) for row in rows),
            "semantic_judgment": PENDING,
        },
    )
