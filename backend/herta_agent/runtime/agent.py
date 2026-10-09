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
from contextlib import aclosing, nullcontext
from functools import partial
from time import perf_counter
from uuid import uuid4

from herta_agent.config import RunSettings
from herta_agent.llm.base import LLMProvider
from herta_agent.llm.streaming import ReplyCompleted, TextDelta
from herta_agent.runtime.context import ContextBuilder, StaticContextBuilder
from herta_agent.runtime.context_engine import ContextEngine
from herta_agent.runtime.errors import (
    ContextError,
    ModelTimeoutError,
    ProviderError,
    ProviderProtocolError,
    StepLimitExceeded,
    ToolCallLimitExceeded,
)
from herta_agent.runtime.events import EventSink, NullSink, RuntimeEvent
from herta_agent.runtime.messages import Message, ModelReply, RunResult
from herta_agent.runtime.session import Session
from herta_agent.runtime.turn import MemoryTurn, TurnIO
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        settings: RunSettings | None = None,
        *,
        registry: ToolRegistry | None = None,
        context_builder: ContextBuilder | None = None,
        streaming: bool = False,
    ) -> None:
        if type(streaming) is not bool or (
            streaming and not callable(getattr(provider, "stream", None))
        ):
            raise ProviderError("流式模式需要提供受支持的stream入口。")
        self.streaming = streaming
        self.provider = provider
        self.settings = settings or RunSettings()
        self.context_engine = ContextEngine(self.settings.context)
        self.registry = registry if registry is not None else ToolRegistry()
        self.executor = ToolExecutor(self.registry, timeout=self.settings.tool_timeout)
        self.context_builder = (
            context_builder if context_builder is not None else StaticContextBuilder()
        )

    async def _request(self, messages, sink, step, message_id):
        if not self.streaming:
            return await self.provider.complete(messages, tools=self.registry.definitions())
        response = None
        stream = self.provider.stream(messages, tools=self.registry.definitions())
        cleanup = (
            aclosing(stream) if callable(getattr(stream, "aclose", None)) else nullcontext(stream)
        )
        async with cleanup:
            async for event in stream:
                if response is not None:
                    raise ProviderProtocolError("完整回复之后仍收到流式事件。")
                if isinstance(event, TextDelta) and isinstance(event.text, str):
                    await sink.emit(
                        RuntimeEvent(
                            type="llm.delta",
                            step=step,
                            message_id=message_id,
                            payload={"text": event.text},
                        )
                    )
                elif isinstance(event, ReplyCompleted) and isinstance(event.reply, ModelReply):
                    try:
                        response = ModelReply.model_validate_json(
                            event.reply.model_dump_json(), strict=True
                        )
                    except ValueError:
                        raise ProviderProtocolError("流式完整回复结构无效。") from None
                else:
                    raise ProviderProtocolError("流式入口返回了不支持的事件。")
        if response is None:
            raise ProviderProtocolError("模型流结束但没有完整回复。")
        return response

    async def run(
        self,
        session: Session,
        user_text: str,
        *,
        turn_io: TurnIO | None = None,
        observer: EventSink | None = None,
    ) -> RunResult:
        """One step is one model request. Every stored call gets exactly one result."""
        user_message = Message(role="user", content=user_text)
        turn = turn_io if turn_io is not None else MemoryTurn(session)
        await turn.begin(user_message)
        sink = observer if observer is not None else NullSink()
        step = 0
        try:
            context = self.context_builder.snapshot()
            await turn.set_context(context.sha256)
            for step in range(1, self.settings.max_steps + 1):
                await asyncio.sleep(0)  # Cancellation checkpoint even for immediate providers.
                message_id = uuid4().hex
                package = self.context_engine.prepare(
                    session.history, context, tools=self.registry.definitions()
                )
                record_context = getattr(turn, "record_context", None)
                if record_context is not None:
                    await record_context(package, step)
                await sink.emit(
                    RuntimeEvent(
                        type="context.prepared",
                        step=step,
                        message_id=message_id,
                        payload=package.diagnostic(step),
                    )
                )
                messages = package.messages
                await sink.emit(RuntimeEvent(type="llm.started", step=step, message_id=message_id))
                try:
                    async with asyncio.timeout(self.settings.request_timeout):
                        response = await self._request(messages, sink, step, message_id)
                except TimeoutError:
                    raise ModelTimeoutError("模型请求超过本轮设置的时间限制。") from None

                if response.message.tool_calls:
                    await turn.append(response.message, message_id=message_id, step=step)
                    await sink.emit(
                        RuntimeEvent(
                            type="llm.completed",
                            step=step,
                            message_id=message_id,
                            payload={"message": response.message.model_dump(mode="json")},
                        )
                    )
                    if step == self.settings.max_steps:
                        raise StepLimitExceeded("达到 max_steps，停止请求模型。")
                    if len(response.message.tool_calls) > 4:
                        raise ToolCallLimitExceeded("模型单次请求超过 4 个工具，已停止当前轮。")
                    for call in response.message.tool_calls:
                        await asyncio.sleep(0)
                        tool_message_id = uuid4().hex

                        on_started = partial(
                            sink.emit,
                            RuntimeEvent(
                                type="tool.started",
                                step=step,
                                message_id=tool_message_id,
                                tool_call_id=call.id,
                                payload={"name": call.name},
                            ),
                        )
                        tool_started = perf_counter()
                        result = await self.executor.execute(call, on_started=on_started)
                        elapsed_ms = round((perf_counter() - tool_started) * 1000, 3)
                        await turn.append(
                            Message(role="tool", tool_call_id=call.id, content=result.to_json()),
                            message_id=tool_message_id,
                            step=step,
                        )
                        await sink.emit(
                            RuntimeEvent(
                                type="tool.completed" if result.ok else "tool.failed",
                                step=step,
                                message_id=tool_message_id,
                                tool_call_id=call.id,
                                payload={
                                    "name": call.name,
                                    "duration_ms": elapsed_ms,
                                    "result": result.model_dump(mode="json"),
                                },
                            )
                        )
                    continue
                await turn.complete(response.message, message_id=message_id, step=step)
                await sink.emit(
                    RuntimeEvent(
                        type="llm.completed",
                        step=step,
                        message_id=message_id,
                        payload={"message": response.message.model_dump(mode="json")},
                    )
                )
                return RunResult(
                    session_id=session.session_id,
                    reply=response.message.content,
                    steps=step,
                    context_hash=context.sha256,
                )
            raise StepLimitExceeded("达到 max_steps，停止请求模型。")
        except asyncio.CancelledError:
            await turn.abort(
                cancelled=True,
                error_code="cancelled",
                safe_message="用户取消当前轮，工具未完成。",
                step=step,
            )
            raise
        except Exception as error:
            code, message = "run_aborted", "当前轮异常结束，工具未完成。"
            if isinstance(error, ContextError):
                code, message = "context_budget_exceeded", str(error)
            elif isinstance(error, StepLimitExceeded):
                code, message = "max_steps_exceeded", "模型请求预算耗尽，未执行此工具。"
            elif isinstance(error, ToolCallLimitExceeded):
                code, message = "tool_call_limit", "每次模型响应最多允许 4 个工具调用，本批未执行。"
            await turn.abort(cancelled=False, error_code=code, safe_message=message, step=step)
            raise
        finally:
            # Also runs on cancellation; CancelledError is deliberately not swallowed.
            session.end_turn()
