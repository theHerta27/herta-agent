"""Build, inspect and evaluate the same retrieval path used by search_knowledge."""

import argparse
import asyncio
import io
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import ValidationError

from herta_agent.rag.embeddings import create_embeddings
from herta_agent.rag.errors import RagError
from herta_agent.rag.ingest import digest, load_corpus
from herta_agent.rag.retriever import Retriever, SearchSettings
from herta_agent.rag.service import (
    DEFAULT_INDEX,
    DEFAULT_KNOWLEDGE,
    DEFAULT_QUESTIONS,
    PROJECT_ROOT,
)
from herta_agent.rag.store import load_index, publish_index
from herta_agent.runtime.errors import AgentError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Herta Phase 4: explicit local RAG commands")
    result.add_argument("--knowledge", type=Path, default=DEFAULT_KNOWLEDGE)
    result.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    result.add_argument("--k", type=int, default=4)
    result.add_argument(
        "--min-score", type=float, default=0.0, help="初始阈值未校准；分数不是置信度"
    )
    sub = result.add_subparsers(dest="action", required=True)
    sub.add_parser("build", help="向所配置服务发送知识片段并发布新索引")
    inspect = sub.add_parser("inspect", help="发送查询，显示排序及过滤原因")
    inspect.add_argument("query")
    evaluate = sub.add_parser("eval", help="直接检索或真实聊天评测；不会自动判定语义正确")
    evaluate.add_argument("--mode", choices=("retrieval", "chat"), default="retrieval")
    evaluate.add_argument("--split", choices=("dev", "check", "all"), default="dev")
    evaluate.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    evaluate.add_argument("--output", type=Path)
    evaluate.add_argument("--soul", type=Path, default=PROJECT_ROOT / "persona" / "soul.md")
    return result


async def command(args: argparse.Namespace, client: httpx.AsyncClient) -> dict:
    settings = SearchSettings(k=args.k, min_score=args.min_score)
    embeddings = create_embeddings(client)
    corpus = load_corpus(args.knowledge)
    if args.action == "build":
        vectors = await embeddings.embed_documents([c.embedding_text for c in corpus.chunks])
        index = publish_index(args.index, corpus, vectors, embeddings.fingerprint, embeddings.model)
        report = {
            "index_id": index.index_id,
            "chunks": len(index.chunks),
            "dimension": index.manifest.dimension,
            "corpus_fingerprint": corpus.fingerprint,
            "embedding_fingerprint": embeddings.fingerprint,
        }
    else:
        index = load_index(args.index, corpus, embeddings.fingerprint)
        retriever = Retriever(index, embeddings, settings)
        if args.action == "inspect":
            report = await retriever.inspect(args.query)
        else:
            from herta_agent.rag.evaluate import evaluate_chat, evaluate_retrieval, load_questions

            questions = load_questions(args.questions, {c.unit_id for c in corpus.chunks})
            if args.mode == "retrieval":
                report = await evaluate_retrieval(retriever, questions, split=args.split)
            else:
                from herta_agent.config import ProviderSettings, RunSettings
                from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
                from herta_agent.persona import PersonaContextBuilder
                from herta_agent.runtime.agent import Agent
                from herta_agent.tools.echo import echo_registry
                from herta_agent.tools.search_knowledge import search_knowledge_spec

                chat_settings = ProviderSettings.from_env()
                registry = echo_registry()
                registry.register(search_knowledge_spec(retriever))
                # Separate client and settings: embedding service need not host chat.
                async with httpx.AsyncClient() as chat_client:
                    agent = Agent(
                        OpenAICompatibleProvider(chat_settings, chat_client),
                        RunSettings(),
                        registry=registry,
                        context_builder=PersonaContextBuilder(args.soul),
                    )
                    report = await evaluate_chat(agent, questions, split=args.split)
                report["chat_model"] = chat_settings.model
                report["run_settings"] = RunSettings().model_dump()
            report.update(
                {
                    "index_manifest": index.manifest.model_dump(),
                    "search_settings": settings.model_dump(),
                    "embedding_config": embeddings.settings.model_dump(mode="json"),
                    "threshold_calibration": "not_yet_validated",
                    "questions_sha256": digest(args.questions.read_bytes()),
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            target = (
                args.output
                or args.index / "reports" / f"{args.mode}-{args.split}-{uuid.uuid4().hex}.json"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
            )
            print(f"评测报告：{target.absolute()}", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return report


async def _run(args):
    # Windows needs periodic event-loop wakeups to deliver Python Ctrl+C promptly.
    loop = asyncio.get_running_loop()

    def pulse():
        nonlocal handle
        handle = loop.call_later(0.1, pulse)

    handle = loop.call_later(0.1, pulse)
    try:
        async with httpx.AsyncClient() as client:
            return await command(args, client)
    finally:
        handle.cancel()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and not stream.isatty():
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("已取消；未发布的新索引不会替换当前版本。", file=sys.stderr)
        raise SystemExit(130) from None
    except RagError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except (AgentError, ValidationError, OSError):
        print("配置、评测输入或文件读写失败，请检查本地设置。", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
