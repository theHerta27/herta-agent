"""Bounded model → tools → model loop.
作为导演，负责一次用户请求来了以后，整个流程怎么推进：
创建用户消息
放进 Session
准备上下文
调用模型
获取回复
保存回复
返回结果
"""

import asyncio

from herta_agent.config import RunSettings
from herta_agent.llm.base import LLMProvider
from herta_agent.runtime.context import ContextBuilder, StaticContextBuilder
from herta_agent.runtime.errors import ModelTimeoutError, StepLimitExceeded, ToolCallLimitExceeded
from herta_agent.runtime.messages import Message, RunResult
from herta_agent.runtime.session import Session
from herta_agent.tools.executor import ToolExecutor, ToolResult
from herta_agent.tools.registry import ToolRegistry


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        settings: RunSettings | None = None,
        *,
        registry: ToolRegistry | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.provider = provider
        self.settings = settings or RunSettings()
        self.registry = registry if registry is not None else ToolRegistry()
        self.executor = ToolExecutor(self.registry, timeout=self.settings.tool_timeout)
        self.context_builder = (
            context_builder if context_builder is not None else StaticContextBuilder()
        )

    async def run(self, session: Session, user_text: str) -> RunResult:
        """One step is one model request. Every stored call gets exactly one result."""
        user_message = Message(role="user", content=user_text)
        session.begin_turn(user_message)
        try:
            session.context_hash = None
            context = self.context_builder.snapshot()
            session.context_hash = context.sha256
            for step in range(1, self.settings.max_steps + 1):
                await asyncio.sleep(0)  # Cancellation checkpoint even for immediate providers.
                messages = context.build_messages(session.history)
                try:
                    async with asyncio.timeout(self.settings.request_timeout):
                        response = await self.provider.complete(
                            messages, tools=self.registry.definitions()
                        )
                except TimeoutError:
                    raise ModelTimeoutError("模型请求超过本轮设置的时间限制。") from None

                if response.message.tool_calls:
                    session.record_calls(response.message)
                    if step == self.settings.max_steps:
                        session.close_pending(
                            ToolResult.failure(
                                "max_steps_exceeded", "模型请求预算耗尽，未执行此工具。"
                            ).to_json()
                        )
                        raise StepLimitExceeded("达到 max_steps，停止请求模型。")
                    if len(response.message.tool_calls) > 4:
                        session.close_pending(
                            ToolResult.failure(
                                "tool_call_limit", "每次模型响应最多允许 4 个工具调用，本批未执行。"
                            ).to_json()
                        )
                        raise ToolCallLimitExceeded("模型单次请求超过 4 个工具，已停止当前轮。")
                    for call in response.message.tool_calls:
                        await asyncio.sleep(0)
                        result = await self.executor.execute(call)
                        session.record_result(call.id, result.to_json())
                    continue
                session.complete_turn(response.message)
                return RunResult(
                    session_id=session.session_id,
                    reply=response.message.content,
                    steps=step,
                    context_hash=context.sha256,
                )
            raise StepLimitExceeded("达到 max_steps，停止请求模型。")
        except asyncio.CancelledError:
            session.close_pending(
                ToolResult.failure("cancelled", "用户取消当前轮，工具未完成。").to_json()
            )
            raise
        except Exception:
            session.close_pending(
                ToolResult.failure("run_aborted", "当前轮异常结束，工具未完成。").to_json()
            )
            raise
        finally:
            # Also runs on cancellation; CancelledError is deliberately not swallowed.
            session.end_turn()
