import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from test_run_admission import GateProvider

from herta_agent.llm.streaming import ReplyCompleted, TextDelta
from herta_agent.runtime.messages import Message, ModelReply
from herta_agent.service.app import create_app
from herta_agent.service.events import EventQueue, encode_event
from herta_agent.service.settings import ServiceSettings
from herta_agent.service.sse import RunResponse


class ServiceSSETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = ServiceSettings(
            db_path=Path(self.temp.name) / "sse.sqlite3",
            send_wait_seconds=0.03,
            heartbeat_seconds=0.02,
            event_wait_seconds=0.03,
        )

    async def test_post_frames_unicode_order_and_no_replay(self):
        class Provider:
            async def stream(self, messages, *, tools=()):
                yield TextDelta("你好\n第二行")
                yield ReplyCompleted(
                    ModelReply(message=Message(role="assistant", content="你好\n第二行"))
                )

        app = create_app(self.settings, provider=Provider())
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://local"
            ) as client:
                sid = (await client.post("/sessions")).json()["session_id"]
                response = await client.post(f"/sessions/{sid}/runs", json={"text": "go"})
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/event-stream", response.headers["content-type"])
                events = [
                    json.loads(line[6:])
                    for line in response.text.splitlines()
                    if line.startswith("data: ")
                ]
                self.assertEqual(
                    [e["type"] for e in events],
                    [
                        "run.started",
                        "context.prepared",
                        "llm.started",
                        "llm.delta",
                        "llm.completed",
                        "run.completed",
                    ],
                )
                self.assertEqual([e["seq"] for e in events], [1, 2, 3, 4, 5, 6])
                self.assertEqual(events[3]["payload"]["text"], "你好\n第二行")
                self.assertIn(f"id: {events[0]['run_id']}:1", response.text)
                again = await client.post(
                    f"/sessions/{sid}/runs",
                    json={"text": "no replay"},
                    headers={"Last-Event-ID": "old:1"},
                )
                self.assertEqual(again.status_code, 400)
                self.assertEqual(len((await client.get(f"/sessions/{sid}")).json()["messages"]), 2)

    async def response_fixture(self):
        app = create_app(self.settings, provider=GateProvider())
        await self.enterAsyncContext(app.router.lifespan_context(app))
        sid = (await app.state.store.create_session()).session_id
        return app, RunResponse(app.state.manager, sid, "go", self.settings)

    async def test_disconnect_during_admission_and_before_first_event(self):
        app, response = await self.response_fixture()
        entered, release = asyncio.Event(), asyncio.Event()
        original = app.state.store.admit_run

        async def admit(*args):
            entered.set()
            await release.wait()
            return await original(*args)

        incoming = asyncio.Queue()
        sent = []

        async def send(message):
            sent.append(message)

        with patch.object(app.state.store, "admit_run", admit):
            task = asyncio.create_task(response({}, incoming.get, send))
            await asyncio.wait_for(entered.wait(), 2)
            incoming.put_nowait({"type": "http.disconnect"})
            release.set()
            await asyncio.wait_for(task, 2)
        self.assertEqual(app.state.manager.active_count, 0)
        history = await app.state.store.load_history(response.session_id)
        self.assertEqual((await app.state.store.get_run(history[0].run_id)).status, "cancelled")

    async def test_disconnect_midstream_cancels_and_heartbeat_is_sent(self):
        app, response = await self.response_fixture()
        incoming = asyncio.Queue()
        saw_heartbeat = asyncio.Event()

        async def send(message):
            if message.get("body", b"").startswith(b": heartbeat"):
                saw_heartbeat.set()
                incoming.put_nowait({"type": "http.disconnect"})

        await asyncio.wait_for(response({}, incoming.get, send), 2)
        await asyncio.wait_for(response.handle.done.wait(), 2)
        self.assertTrue(saw_heartbeat.is_set())
        self.assertEqual(
            (await app.state.store.get_run(response.handle.run_id)).status, "cancelled"
        )

    async def test_stalled_send_has_deadline_and_cancels_owner(self):
        app, response = await self.response_fixture()

        async def send(message):
            await asyncio.Event().wait()

        await asyncio.wait_for(response({}, asyncio.Queue().get, send), 2)
        await asyncio.wait_for(response.handle.done.wait(), 2)
        self.assertEqual(
            (await app.state.store.get_run(response.handle.run_id)).status, "cancelled"
        )

    async def test_event_buffer_byte_limit_and_safe_encoding(self):
        queue = EventQueue()
        event = {
            "schema_version": 1,
            "type": "llm.delta",
            "run_id": "r",
            "session_id": "s",
            "seq": 1,
            "timestamp": "now",
            "payload": {"text": "x" * 100},
        }
        encoded = encode_event(event)
        with patch("herta_agent.service.events.MAX_BUFFER_BYTES", len(encoded)):
            queue.put_nowait(event)
            with self.assertRaises(asyncio.QueueFull):
                queue.put_nowait(event)
            self.assertEqual(queue.get_nowait(), event)
            await queue.put(event)
        with patch("herta_agent.service.events.MAX_EVENT_BYTES", 20), self.assertRaises(ValueError):
            encode_event(event)

    async def test_producer_backpressure_cancels_without_waiting_for_consumer(self):
        class Provider:
            async def stream(self, messages, *, tools=()):
                for _ in range(200):
                    yield TextDelta("x")

        app = create_app(self.settings, provider=Provider())
        async with app.router.lifespan_context(app):
            sid = (await app.state.store.create_session()).session_id
            handle = await app.state.manager.submit(sid, "go")
            await asyncio.wait_for(handle.done.wait(), 2)
            self.assertEqual((await app.state.store.get_run(handle.run_id)).status, "cancelled")
            self.assertLessEqual(handle.events.qsize(), 128)

    async def test_rag_summary_follows_committed_tool_event(self):
        from herta_agent.runtime.events import RuntimeEvent
        from herta_agent.service.runs import RunHandle

        handle = RunHandle("r", "s")
        await handle.emit(
            RuntimeEvent(
                type="tool.completed",
                step=1,
                message_id="m",
                tool_call_id="t",
                payload={
                    "name": "search_knowledge",
                    "result": {
                        "ok": True,
                        "data": {
                            "query": "黑塔",
                            "index_id": "i",
                            "chunks": [
                                {"id": "c", "source": "story.md", "score": 0.7, "text": "full text"}
                            ],
                        },
                    },
                },
            )
        )
        self.assertEqual(handle.events.get_nowait()["type"], "tool.completed")
        summary = handle.events.get_nowait()
        self.assertEqual(summary["type"], "rag.retrieved")
        self.assertEqual(summary["payload"]["chunks"][0]["source"], "story.md")
        self.assertNotIn("full text", json.dumps(summary))

    async def test_lost_completion_notification_preserves_committed_fact(self):
        class Provider:
            async def complete(self, messages, *, tools=()):
                return ModelReply(message=Message(role="assistant", content="done"))

        app = create_app(self.settings, provider=Provider())
        async with app.router.lifespan_context(app):
            sid = (await app.state.store.create_session()).session_id
            response = RunResponse(app.state.manager, sid, "go", self.settings)

            async def send(message):
                if b"event: run.completed" in message.get("body", b""):
                    raise OSError("connection lost")

            await response({}, asyncio.Queue().get, send)
            self.assertEqual(
                (await app.state.store.get_run(response.handle.run_id)).status, "completed"
            )
            self.assertEqual(len(await app.state.store.load_history(sid)), 2)

    async def test_cancelled_run_does_not_send_buffered_delta(self):
        yielded = asyncio.Event()

        class Provider:
            async def stream(self, messages, *, tools=()):
                yield TextDelta("not yet displayed")
                yielded.set()
                await asyncio.Event().wait()

        app = create_app(self.settings, provider=Provider())
        async with app.router.lifespan_context(app):
            sid = (await app.state.store.create_session()).session_id
            response = RunResponse(
                app.state.manager,
                sid,
                "go",
                self.settings.model_copy(update={"send_wait_seconds": 2.0}),
            )
            types = []

            async def send(message):
                if message["type"] == "http.response.start":
                    await yielded.wait()
                    await app.state.manager.cancel(response.handle.run_id)
                    await response.handle.done.wait()
                elif message.get("body", b"").startswith(b"id:"):
                    types.append(
                        next(
                            line[7:]
                            for line in message["body"].decode().splitlines()
                            if line.startswith("event: ")
                        )
                    )

            await response({}, asyncio.Queue().get, send)
            self.assertNotIn("llm.delta", types)
            self.assertEqual(types[-1], "run.cancelled")
