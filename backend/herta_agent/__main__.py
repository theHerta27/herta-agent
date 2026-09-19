"""Teaching CLI. Default mode is offline; real HTTP calls require --provider openai."""

import argparse
import asyncio
import getpass
import io
import os
import sys

import httpx
from pydantic import ValidationError

from herta_agent.config import ProviderSettings, RunSettings
from herta_agent.llm.demo import DemoProvider
from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import AgentError
from herta_agent.runtime.session import Session


async def chat(agent: Agent, message: str | None) -> None:
    session = Session()
    if message is not None:
        result = await agent.run(session, message)
        print(f"Assistant: {result.reply}\n[steps={result.steps}]")
        return

    print("输入 /exit 退出；Ctrl+C 取消并退出。本阶段历史仅存在于当前进程。")
    while True:
        # This teaching CLI is idle here; no model task is running during input().
        try:
            text = input("You: ")  # noqa: ASYNC250 -- CLI is idle; no active background runs.
        except EOFError:
            return
        if text.strip() == "/exit":
            return
        if not text.strip():
            continue
        try:
            result = await agent.run(session, text)
        except AgentError as exc:
            print(f"错误：{exc}", file=sys.stderr)
        else:
            print(f"Assistant: {result.reply}\n[steps={result.steps}]")


async def run_cli(args: argparse.Namespace) -> None:
    settings = RunSettings(max_steps=args.max_steps, request_timeout=args.timeout)
    if args.provider == "demo":
        print("模式：离线演示（固定逻辑，不调用 LLM，不读取 API Key）")
        await chat(Agent(DemoProvider(), settings), args.message)
        return

    base_url = os.environ.get("HERTA_BASE_URL", "")
    model = os.environ.get("HERTA_MODEL", "")
    if not base_url or not model:
        raise AgentError("请先设置 HERTA_BASE_URL 和 HERTA_MODEL。")
    key = os.environ.get("HERTA_API_KEY") or getpass.getpass("API Key（不回显、不保存）: ")
    provider_settings = ProviderSettings(base_url=base_url, model=model, api_key=key)
    print("模式：真实模型（非流式）")
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout, connect=10)
    ) as client:
        provider = OpenAICompatibleProvider(provider_settings, client)
        await chat(Agent(provider, settings), args.message)


def main() -> None:
    # Windows pipes may default to a legacy encoding. Keep redirected CLI I/O UTF-8.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and not stream.isatty():
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Herta Agent — Phase 1 teaching runtime")
    parser.add_argument("--provider", choices=("demo", "openai"), default="demo")
    parser.add_argument("--message", help="发送一条消息后退出；省略则进入交互模式")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=120.0, help="每次模型请求总期限（秒）")
    args = parser.parse_args()
    try:
        asyncio.run(run_cli(args))
    except KeyboardInterrupt:
        print("\n已取消，退出。", file=sys.stderr)
        raise SystemExit(130) from None
    except (AgentError, ValidationError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
