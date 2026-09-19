"""The Phase 1 loop skeleton: bounded request → complete text → commit history."""

import asyncio

from herta_agent.config import RunSettings
from herta_agent.llm.base import LLMProvider
from herta_agent.runtime.errors import ModelTimeoutError, StepLimitExceeded
from herta_agent.runtime.messages import Message, RunResult
from herta_agent.runtime.session import Session

DEFAULT_SYSTEM = "You are a helpful assistant. Answer clearly and accurately."


class Agent:
    def __init__(self, provider: LLMProvider, settings: RunSettings | None = None) -> None:
        self.provider = provider
        self.settings = settings or RunSettings()

    async def run(self, session: Session, user_text: str) -> RunResult:
        """Run one user turn. A successful Phase 1 turn always uses exactly one step.

        The bounded loop is the extension point for Phase 2 tool results. We do not
        fabricate extra model calls, auto-retry, or auto-continue truncated replies.
        """
        user_message = Message(role="user", content=user_text)
        session.begin_turn(user_message)
        try:
            for step in range(1, self.settings.max_steps + 1):
                messages = (Message(role="system", content=DEFAULT_SYSTEM), *session.history)
                try:
                    async with asyncio.timeout(self.settings.request_timeout):
                        response = await self.provider.complete(messages)
                except TimeoutError:
                    raise ModelTimeoutError("模型请求超过本轮设置的时间限制。") from None

                # Phase 2 will insert the tool-call branch here and continue the loop.
                session.complete_turn(response.message)
                return RunResult(
                    session_id=session.session_id, reply=response.message.content, steps=step
                )
            # Reserved for the future continue/tool path; not reachable in Phase 1.
            raise StepLimitExceeded("达到 max_steps，停止请求模型。")
        finally:
            # Also runs on cancellation; CancelledError is deliberately not swallowed.
            session.end_turn()
