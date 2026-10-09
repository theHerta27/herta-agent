"""Offline C0/C1/C2 contract probe. No HTTP provider and no model capability scores."""

import argparse
import asyncio
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from herta_agent.config import RunSettings
from herta_agent.persona import PersonaContextBuilder
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.context_engine import ContextEngine, ContextSettings
from herta_agent.runtime.messages import Message, ModelReply
from herta_agent.runtime.session import Session

ROOT = Path(__file__).resolve().parents[2]


class FullHistoryBaseline:
    def __init__(self, settings):
        self.engine = ContextEngine(
            ContextSettings(
                window_tokens=2000000,
                output_reserve=settings.output_reserve,
                summary_enabled=False,
            )
        )
        self.budget = (
            settings.window_tokens - settings.output_reserve - settings.safety_margin
        )

    def prepare(self, history, snapshot, *, tools=()):
        package = self.engine.prepare(history, snapshot, tools=tools)
        return replace(
            package, input_budget=self.budget, policy_version="C0-full-history"
        )


class FixtureReader:
    """Reads a literal marker; deliberately does not simulate reasoning or real LLM quality."""

    def __init__(self, marker):
        self.marker = marker
        self.requests = 0

    async def complete(self, messages, *, tools=()):
        self.requests += 1
        visible = any(self.marker in (message.content or "") for message in messages)
        return ModelReply(
            message=Message(
                role="assistant",
                content=self.marker if visible else "fixture_marker_absent",
            )
        )


async def run():
    raw = (ROOT / "evals/harness/cases.json").read_bytes()
    config = json.loads(raw)
    case = config["context_probe"]
    history = [
        Message(role="user", content=case["initial_user"]),
        Message(role="assistant", content=case["initial_assistant"]),
    ]
    for index in range(case["distraction_rounds"]):
        history.extend(
            (
                Message(
                    role="user",
                    content=f"无关轮次 {index}："
                    + case["distraction_sentence"] * case["sentence_repeats"],
                ),
                Message(role="assistant", content="这轮讨论结束。"),
            )
        )
    results = []
    for mode in ("C0", "C1", "C2"):
        settings = ContextSettings(
            window_tokens=case["window_tokens"],
            output_reserve=case["output_reserve"],
            summary_tokens=case["summary_tokens"],
            summary_enabled=mode == "C2",
        )
        provider = FixtureReader(case["expected_marker"])
        agent = Agent(
            provider,
            RunSettings(context=settings),
            context_builder=PersonaContextBuilder(ROOT / "persona/soul.md"),
        )
        if mode == "C0":
            agent.context_engine = FullHistoryBaseline(settings)
        events = []

        class Sink:
            def __init__(self, collected):
                self.events = collected

            async def emit(self, event):
                if event.type == "context.prepared":
                    self.events.append(event.payload)

        session = Session.restore(f"offline-{mode}", history)
        started = perf_counter()
        result = await agent.run(session, case["final_user"], observer=Sink(events))
        diagnostic = events[-1]
        results.append(
            {
                "policy": mode,
                **diagnostic,
                "elapsed_seconds": perf_counter() - started,
                "fixture_marker_visible": result.reply == case["expected_marker"],
                "within_estimated_budget": (
                    diagnostic["estimated_input_tokens"] <= diagnostic["input_budget"]
                ),
                "fixture_provider_requests": provider.requests,
                "original_history_unchanged": session.history[: len(history)]
                == tuple(history),
            }
        )
    return {
        "dataset_version": config["version"],
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "created_at": datetime.now(UTC).isoformat(),
        "execution": "offline_contract_probe",
        "network_requests": 0,
        "actual_model_quality": "not_evaluated",
        "actual_token_usage": None,
        "limitations": [
            "FixtureReader只检查文字能否被上下文选择保留，不证明模型理解或回答质量。",
            "Token为可替换词法估算；不是供应商计费或精确Tokenizer。",
            "C0故意保留旧版完整历史，可能超过配置预算；不是产品默认策略。",
        ],
        "cases": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".local/harness-offline-report.json"
    )
    args = parser.parse_args()
    report = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "execution": report["execution"],
                "network_requests": 0,
                "cases": [
                    {
                        key: row[key]
                        for key in (
                            "policy",
                            "estimated_input_tokens",
                            "input_budget",
                            "omitted_message_count",
                            "fixture_marker_visible",
                            "within_estimated_budget",
                            "original_history_unchanged",
                        )
                    }
                    for row in report["cases"]
                ],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
