"""Store first, memory second. Terminal decisions belong to the RunManager."""

import asyncio

from herta_agent.runtime.session import Session
from herta_agent.runtime.turn import MemoryTurn
from herta_agent.storage.models import MessageRecord


class PersistentTurn(MemoryTurn):
    def __init__(self, session, store, handle, manager):
        super().__init__(session)
        self.store, self.handle, self.manager = store, handle, manager

    async def begin(self, user):
        admission = self.handle.admission
        if user != admission.user.message or len(self.session.history) != admission.user.seq - 1:
            raise ValueError("Admission does not match restored history")
        await super().begin(user)

    async def set_context(self, context_hash):
        await self.store.set_context(self.handle.run_id, context_hash)
        await super().set_context(context_hash)

    async def record_context(self, package, step):
        if self.handle.cancel_requested:
            raise asyncio.CancelledError
        await self.store.record_context(self.handle.run_id, step, package)

    async def append(self, message, *, message_id, step):
        if self.handle.cancel_requested:
            raise asyncio.CancelledError
        self.handle.step = step
        await self.store.append_message(self.handle.run_id, message_id, step, message)
        await super().append(message, message_id=message_id, step=step)

    async def complete(self, message, *, message_id, step):
        self.handle.step = step
        final = MessageRecord(
            message_id=message_id,
            session_id=self.session.session_id,
            run_id=self.handle.run_id,
            seq=len(self.session.history) + 1,
            step=step,
            message=message,
        )
        run = await self.manager._finish(self.handle, "completed", final_message=final)
        if run.status != "completed":
            raise asyncio.CancelledError
        await super().complete(message, message_id=message_id, step=step)

    async def abort(self, *, cancelled, error_code, safe_message, step):
        self.handle.step = step
        await self.manager._finish(
            self.handle,
            "cancelled" if cancelled else "failed",
            error=f"{error_code}: {safe_message}",
        )
        history = await self.store.load_history(self.handle.session_id)
        self.session = Session.restore(self.handle.session_id, [r.message for r in history])
