"""Teaching CLI. Default mode is offline; real HTTP calls require --provider openai."""

import argparse
import asyncio
import io
import sys
from pathlib import Path

import httpx
from pydantic import ValidationError

from herta_agent.config import ProviderSettings, RunSettings
from herta_agent.llm.demo import DemoProvider, ToolDemoProvider
from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
from herta_agent.persona import PersonaContextBuilder
from herta_agent.rag.errors import RagError
from herta_agent.rag.retriever import SearchSettings
from herta_agent.rag.service import DEFAULT_INDEX, DEFAULT_KNOWLEDGE, load_retriever
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import AgentError
from herta_agent.runtime.messages import RunResult
from herta_agent.runtime.session import Session
from herta_agent.tools.echo import echo_registry
from herta_agent.tools.search_knowledge import search_knowledge_spec

DEFAULT_SOUL_PATH = Path(__file__).resolve().parents[2] / "persona" / "soul.md"


def print_result(result: RunResult) -> None:
    print(f"Assistant: {result.reply}\n[steps={result.steps}]")
    print(f"[context_sha256={result.context_hash}]")


async def run_turn(agent: Agent, session: Session, text: str) -> RunResult:
    """Keep Windows' event loop waking so Python can dispatch pending Ctrl+C."""
    loop = asyncio.get_running_loop()

    def pulse() -> None:
        nonlocal handle
        handle = loop.call_later(0.1, pulse)

    handle = loop.call_later(0.1, pulse)
    try:
        return await agent.run(session, text)
    finally:
        handle.cancel()


def chat(agent: Agent, message: str | None, runner: asyncio.Runner) -> None:
    session = Session()
    if message is not None:
        result = runner.run(run_turn(agent, session, message))
        print_result(result)
        return

    print("输入 /exit 退出；Ctrl+C 取消当前轮并保留会话。本阶段历史仅存在于当前进程。")
    while True:
        # This teaching CLI is idle here; no model task is running during input().
        try:
            text = input("You: ")
        except EOFError:
            return
        except KeyboardInterrupt:
            print("\n已取消输入；输入 /exit 退出。")
            continue
        if text.strip() == "/exit":
            return
        if not text.strip():
            continue
        try:
            result = runner.run(run_turn(agent, session, text))
        except KeyboardInterrupt:
            print("\n已取消当前轮，会话已保留。", file=sys.stderr)
        except AgentError as exc:
            print(f"错误：{exc}", file=sys.stderr)
        else:
            print_result(result)


def run_cli(args: argparse.Namespace, runner: asyncio.Runner) -> None:
    settings = RunSettings(
        max_steps=args.max_steps, request_timeout=args.timeout, tool_timeout=args.tool_timeout
    )
    registry = echo_registry()
    context_builder = PersonaContextBuilder(args.soul.absolute())
    if args.provider == "demo":
        print("模式：离线演示（固定逻辑，不调用 LLM，不读取 API Key）")
        provider = ToolDemoProvider(args.demo_delay) if args.demo_tools else DemoProvider()
        chat(
            Agent(provider, settings, registry=registry, context_builder=context_builder),
            args.message,
            runner,
        )
        return

    provider_settings = ProviderSettings.from_env()
    search_settings = SearchSettings(k=args.rag_k, min_score=args.rag_min_score)
    print("模式：真实模型（非流式）")
    client = httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout, connect=10))
    embedding_client = httpx.AsyncClient()
    try:
        try:
            retriever = load_retriever(
                embedding_client, args.knowledge, args.rag_index, search_settings
            )
        except RagError as exc:
            print(f"知识检索不可用 [{exc.code}]：{exc} 普通聊天仍可继续。", file=sys.stderr)
            registry.register(search_knowledge_spec(unavailable=exc, timeout=args.rag_timeout))
        else:
            registry.register(search_knowledge_spec(retriever, timeout=args.rag_timeout))
            print(f"[rag_index={retriever.index.index_id}; 阈值尚待真实评测校准]")
        provider = OpenAICompatibleProvider(provider_settings, client)
        chat(
            Agent(provider, settings, registry=registry, context_builder=context_builder),
            args.message,
            runner,
        )
    finally:
        runner.run(embedding_client.aclose())
        runner.run(client.aclose())


def main() -> None:
    # Windows pipes may default to a legacy encoding. Keep redirected CLI I/O UTF-8.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and not stream.isatty():
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Herta Agent — Phase 4 teaching runtime")
    parser.add_argument("--provider", choices=("demo", "openai"), default="demo")
    parser.add_argument("--message", help="发送一条消息后退出；省略则进入交互模式")
    parser.add_argument(
        "--soul",
        type=Path,
        default=DEFAULT_SOUL_PATH,
        help="必需的 UTF-8 人格文件；默认项目 persona/soul.md",
    )
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=120.0, help="每次模型请求总期限（秒）")
    parser.add_argument("--tool-timeout", type=float, default=10.0, help="每个工具执行期限（秒）")
    parser.add_argument("--demo-tools", action="store_true", help="离线演示真实工具执行闭环")
    parser.add_argument("--knowledge", type=Path, default=DEFAULT_KNOWLEDGE)
    parser.add_argument("--rag-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--rag-k", type=int, default=4)
    parser.add_argument("--rag-min-score", type=float, default=0.0)
    parser.add_argument("--rag-timeout", type=float, default=20.0)
    parser.add_argument(
        "--demo-delay", type=float, default=0.0, help="离线 echo 延时 0–30 秒，用于验证取消/超时"
    )
    args = parser.parse_args()
    if args.demo_tools and args.provider != "demo":
        parser.error("--demo-tools 仅用于 --provider demo")
    if args.demo_delay != 0 and not args.demo_tools:
        parser.error("--demo-delay 需要 --demo-tools")
    try:
        with asyncio.Runner() as runner:
            run_cli(args, runner)
    except KeyboardInterrupt:
        print("\n已取消，退出。", file=sys.stderr)
        raise SystemExit(130) from None
    except (AgentError, ValidationError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
