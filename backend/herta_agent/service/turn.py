"""HTTP RunManager adds its existing cancellation and terminal ownership policy."""

import asyncio

from herta_agent.storage.turn import StoredTurn


class PersistentTurn(StoredTurn):
    def __init__(self, session, store, handle, manager):
        super().__init__(session, store, handle.admission)
        self.handle, self.manager = handle, manager

    def check_cancelled(self):
        if self.handle.cancel_requested:
            raise asyncio.CancelledError

    async def _finish(self, status, *, final_message=None, error=None):
        self.handle.step = self.step
        return await self.manager._finish(
            self.handle,
            status,
            final_message=final_message,
            error=error,
        )
