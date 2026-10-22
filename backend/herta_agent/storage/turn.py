"""Shared store-first TurnIO, independent of CLI and HTTP transport."""

import asyncio

from herta_agent.runtime.session import Session
from herta_agent.runtime.turn import MemoryTurn
from herta_agent.storage.models import MessageRecord


class StoredTurn(MemoryTurn):
    def __init__(self, session, store, admission):
        super().__init__(session)
        self.store, self.admission = store, admission
        self.step = 0
        self._finalizing = None
        self._terminal = None

    def check_cancelled(self):
        """Transport owners may add a cancellation gate before each write."""

    async def begin(self, user):
        admission = self.admission
        if user != admission.user.message or len(self.session.history) != admission.user.seq - 1:
            raise ValueError("Admission does not match restored history")
        await super().begin(user)

    async def set_context(self, context_hash):
        await self.store.set_context(self.admission.run.run_id, context_hash)
        await super().set_context(context_hash)

    async def record_context(self, package, step):
        self.check_cancelled()
        self.step = step
        await self.store.record_context(self.admission.run.run_id, step, package)

    async def append(self, message, *, message_id, step):
        self.check_cancelled()
        self.step = step
        await self.store.append_message(self.admission.run.run_id, message_id, step, message)
        await super().append(message, message_id=message_id, step=step)

    async def complete(self, message, *, message_id, step):
        self.step = step
        final = MessageRecord(
            message_id=message_id,
            session_id=self.session.session_id,
            run_id=self.admission.run.run_id,
            seq=len(self.session.history) + 1,
            step=step,
            message=message,
        )
        run = await self._finish("completed", final_message=final)
        if run.status != "completed":
            raise asyncio.CancelledError
        await super().complete(message, message_id=message_id, step=step)

    async def _finish(self, status, *, final_message=None, error=None):
        # Once a terminal commit starts, it owns the result even across Ctrl+C.
        if self._terminal is not None:
            return self._terminal
        if self._finalizing is None:
            self._finalizing = asyncio.create_task(
                self.store.finish_run(
                    self.admission.run.run_id,
                    status,
                    steps=self.step,
                    final_message=final_message,
                    error=error,
                )
            )
        while not self._finalizing.done():
            try:
                await asyncio.shield(self._finalizing)
            except asyncio.CancelledError:
                continue
        self._terminal = self._finalizing.result()
        return self._terminal

    async def abort(self, *, cancelled, error_code, safe_message, step):
        self.step = step
        await self._finish(
            "cancelled" if cancelled else "failed",
            error=f"{error_code}: {safe_message}",
        )
        history = await self.store.load_history(self.session.session_id)
        self.session = Session.restore(self.session.session_id, [r.message for r in history])
