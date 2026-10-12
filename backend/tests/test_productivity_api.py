import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from herta_agent.companion.context import CompanionContext
from herta_agent.runtime.context import StaticContextBuilder
from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings


class TaskProvider:
    def __init__(self):
        self.results = []

    async def complete(self, messages, *, tools=()):
        if messages[-1].role == "tool":
            self.results.append(json.loads(messages[-1].content))
            return ModelReply(message=Message(role="assistant", content="任务工具已检查"))
        return ModelReply(
            message=Message(
                role="assistant",
                tool_calls=(
                    ToolCall(
                        id="task-call",
                        name="create_task",
                        arguments=json.dumps(
                            {
                                "title": "本地学习任务",
                                "due_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                                "remind": True,
                            }
                        ),
                    ),
                ),
            )
        )


class ProductivityAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_control_token_role_and_same_loop_task_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            provider = TaskProvider()
            app = create_app(
                ServiceSettings(
                    db_path=Path(folder) / "sessions.sqlite3", workspace_token="private-control"
                ),
                provider=provider,
            )
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://local"
                ) as client:
                    self.assertEqual((await client.get("/productivity")).status_code, 401)
                    headers = {"Authorization": "Bearer private-control"}
                    self.assertEqual(
                        (
                            await client.post(
                                "/productivity/role", headers=headers, json={"role": "tutor"}
                            )
                        ).status_code,
                        200,
                    )
                    context = CompanionContext(
                        StaticContextBuilder(), app.state.companion
                    ).snapshot()
                    self.assertIn("作为老师", context.system_text)
                    self.assertIn("不改变工具权限", context.system_text)
                    session = (await client.post("/sessions", json={})).json()["session_id"]
                    response = await client.post(
                        f"/sessions/{session}/runs", json={"text": "一小时后提醒我学习"}
                    )
                    self.assertIn("run.completed", response.text)
                    self.assertTrue(provider.results[-1]["ok"])
                    tasks = (await client.get("/productivity", headers=headers)).json()["tasks"]
                    self.assertEqual(len(tasks), 1)
                    prefs = app.state.companion.snapshot()["preferences"]
                    app.state.companion.update_preferences({**prefs, "allow_tools": False})
                    await client.post(f"/sessions/{session}/runs", json={"text": "再次创建"})
                    self.assertFalse(provider.results[-1]["ok"])
                    self.assertEqual(len(app.state.companion.productivity.snapshot()["tasks"]), 1)
                    self.assertEqual(
                        (
                            await client.post(
                                "/productivity/role", headers=headers, json={"role": "shell"}
                            )
                        ).status_code,
                        422,
                    )
                    self.assertEqual(
                        (
                            await client.post(
                                "/productivity/tasks",
                                headers=headers,
                                json={"title": "bad", "due_at": "2026-10-12T20:00:00"},
                            )
                        ).status_code,
                        422,
                    )


if __name__ == "__main__":
    unittest.main()
