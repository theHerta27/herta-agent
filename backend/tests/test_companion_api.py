import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings


class ReminderProvider:
    async def complete(self, messages, *, tools=()):
        if messages[-1].role == "tool":
            data = json.loads(messages[-1].content)
            return ModelReply(
                message=Message(
                    role="assistant", content="已创建提醒" if data["ok"] else "工具已关闭"
                )
            )
        return ModelReply(
            message=Message(
                role="assistant",
                tool_calls=(
                    ToolCall(
                        id="daily",
                        name="create_reminder",
                        arguments='{"title":"喝水","delay_minutes":25}',
                    ),
                ),
            )
        )


class CompanionAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_same_agent_creates_reminder_and_revocation_blocks_next_run(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = ServiceSettings(db_path=Path(folder) / "sessions.db")
            app = create_app(settings, provider=ReminderProvider())
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://local"
                ) as client:
                    session = (await client.post("/sessions", json={})).json()["session_id"]
                    first = await client.post(
                        f"/sessions/{session}/runs", json={"text": "25分钟后提醒喝水"}
                    )
                    self.assertIn("run.completed", first.text)
                    data = (await client.get("/companion")).json()
                    self.assertEqual(data["reminders"][0]["title"], "喝水")
                    prefs = {**data["preferences"], "allow_tools": False}
                    self.assertEqual(
                        (await client.put("/companion/preferences", json=prefs)).status_code, 200
                    )
                    second = await client.post(
                        f"/sessions/{session}/runs", json={"text": "再建提醒"}
                    )
                    self.assertIn("run.completed", second.text)
                    self.assertEqual(len((await client.get("/companion")).json()["reminders"]), 1)
                    invalid = await client.post(
                        "/companion/music/control", json={"action": "volume", "volume": 101}
                    )
                    self.assertEqual(invalid.status_code, 422)
                    self.assertEqual(
                        (await client.get("/companion/music/media/unknown")).status_code, 404
                    )
                    now = datetime.now(UTC)
                    for due in (now - timedelta(minutes=1), now + timedelta(days=731)):
                        invalid = await client.post(
                            "/companion/reminders",
                            json={"title": "无效日期", "due_at": due.isoformat(), "repeat": "once"},
                        )
                        self.assertEqual(invalid.status_code, 422)


if __name__ == "__main__":
    unittest.main()
