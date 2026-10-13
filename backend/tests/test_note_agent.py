import json
import tempfile
import unittest
from pathlib import Path

import httpx

from herta_agent.runtime.messages import Message, ModelReply, ToolCall
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry
from herta_agent.workspace.paths import WorkspaceError
from herta_agent.workspace.tools import workspace_tools


class NoteAgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.root = self.folder / "资料"
        self.root.mkdir()
        (self.root / "asyncio.md").write_text("协程可以在等待时让出执行权。", encoding="utf-8")
        self.preview = "# asyncio复习\n\n协程在等待时让出执行权。\n来源：asyncio.md#行1\n"
        owner = self

        class Provider:
            async def complete(self, messages, *, tools=()):
                if messages[-1].role == "tool":
                    result = json.loads(messages[-1].content)
                    owner.result = result
                    return ModelReply(message=Message(role="assistant", content="待确认，未保存。"))
                names = [s["function"]["name"] for s in tools]
                owner.assertIn("propose_workspace_note", names)
                return ModelReply(
                    message=Message(
                        role="assistant",
                        tool_calls=(
                            ToolCall(
                                id="note",
                                name="propose_workspace_note",
                                arguments=json.dumps(
                                    {
                                        "root_id": owner.root_id,
                                        "target": "复习/asyncio提纲.md",
                                        "text": owner.preview,
                                    }
                                ),
                            ),
                        ),
                    )
                )

        self.app = create_app(
            ServiceSettings(
                db_path=self.folder / "sessions.sqlite3", workspace_token="test-desktop"
            ),
            provider=Provider(),
        )
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.w = self.app.state.workspace
        self.root_id = self.w.grant(str(self.root))["id"]
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://local",
            headers={"Authorization": "Bearer test-desktop"},
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)
        self.temp.cleanup()

    def executor(self):
        registry = ToolRegistry()
        for spec in workspace_tools(self.w):
            registry.register(spec)
        return ToolExecutor(
            registry, tool_policy=lambda spec: spec.name == "propose_workspace_note"
        )

    async def status(self, plan_id):
        return await self.executor().execute(
            ToolCall(
                id="status",
                name="workspace_file_status",
                arguments=json.dumps({"root_id": self.root_id, "plan_id": plan_id}),
            )
        )

    async def test_discovery_stays_visible_without_sharing_and_explains_empty_scope(self):
        registry = ToolRegistry()
        for spec in workspace_tools(self.w):
            registry.register(spec)
        self.assertEqual(
            [s["function"]["name"] for s in registry.definitions()], ["list_workspace_roots"]
        )
        result = await self.executor().execute(
            ToolCall(id="roots", name="list_workspace_roots", arguments="{}")
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data, [])

    async def test_chat_result_route_rejects_unshared_read_while_local_preview_remains(self):
        local = await self.client.get(f"/workspace/roots/{self.root_id}/text?path=asyncio.md")
        self.assertEqual(local.status_code, 200)
        denied = await self.client.get(
            f"/workspace/roots/{self.root_id}/text?path=asyncio.md&shared=true"
        )
        self.assertEqual(denied.status_code, 422)
        self.w.share(self.root_id, True)
        allowed = await self.client.get(
            f"/workspace/roots/{self.root_id}/text?path=asyncio.md&shared=true"
        )
        self.assertEqual(allowed.status_code, 200)

    async def test_result_read_returns_actual_file_hash_for_verification(self):
        import hashlib

        result = self.w.read_text(self.root_id, "asyncio.md")
        self.assertEqual(
            result.get("source_hash"),
            hashlib.sha256((self.root / "asyncio.md").read_bytes()).hexdigest(),
        )

    async def test_old_completed_plan_status_is_not_lost_after_twenty_later_jobs(self):
        from datetime import UTC, datetime, timedelta

        self.w.share(self.root_id, True)
        first = self.w.documents.note(self.root_id, "first.md", "# first", require_vault=False)
        self.w.files.confirm(first["id"], first["digest"], "first")
        await self.w.files.wait()
        for index in range(21):
            plan = self.w.documents.note(
                self.root_id, f"later{index}.md", "# later", require_vault=False
            )
            self.w._write(
                "INSERT INTO file_jobs(id,plan_id,root_id,request_id,status,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (
                    f"history{index}",
                    plan["id"],
                    self.root_id,
                    f"history{index}",
                    "completed",
                    (datetime.now(UTC) + timedelta(seconds=index + 1)).isoformat(),
                ),
            )
        result = await self.status(first["id"])
        self.assertTrue(result.ok)
        self.assertEqual(result.data["status"], "completed")
        state = await self.client.get(f"/workspace/plans/{first['id']}/state")
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()["job"]["status"], "completed")
        self.assertNotIn(str(self.root), json.dumps(state.json()))
        self.w.share(self.root_id, False)
        self.assertEqual(
            (await self.client.get(f"/workspace/plans/{first['id']}/state")).status_code, 422
        )

    async def test_existing_loop_proposes_note_without_vault_then_same_executor_publishes(self):
        self.w.share(self.root_id, True)
        session = (await self.client.post("/sessions", json={})).json()["session_id"]
        response = await self.client.post(
            f"/sessions/{session}/runs", json={"text": "整理笔记，保存前给我确认"}
        )
        self.assertIn("run.completed", response.text)
        self.assertTrue(self.result["ok"])
        data = self.result["data"]
        self.assertEqual(data["text_preview"], self.preview)
        self.assertNotIn(str(self.root), json.dumps(data))
        destination = self.root / "复习/asyncio提纲.md"
        self.assertFalse(destination.exists())
        plan = self.w.plans.get(data["plan_id"])
        self.assertEqual((await self.status(plan["id"])).data["status"], "awaiting_confirmation")
        job = self.w.files.confirm(plan["id"], plan["digest"], "native-confirm")
        await self.w.files.wait()
        status = await self.status(plan["id"])
        self.assertTrue(status.ok)
        self.assertEqual(status.data["status"], "completed")
        self.assertEqual(status.data["job_id"], job["id"])
        self.assertEqual(destination.read_text(encoding="utf-8"), self.preview)
        self.assertIsNone(self.w.documents.settings()["vault_root_id"])

    async def test_note_tool_and_status_recheck_shared_scope_and_confirmation_rejects_revoke(self):
        call = ToolCall(
            id="note",
            name="propose_workspace_note",
            arguments=json.dumps(
                {"root_id": self.root_id, "target": "new.md", "text": self.preview}
            ),
        )
        self.assertFalse((await self.executor().execute(call)).ok)
        self.w.share(self.root_id, True)
        result = await self.executor().execute(call)
        self.assertTrue(result.ok)
        plan = self.w.plans.get(result.data["plan_id"])
        self.w.share(self.root_id, False)
        self.assertFalse((await self.status(plan["id"])).ok)
        with self.assertRaises(WorkspaceError):
            self.w.files.confirm(plan["id"], plan["digest"], "revoked")
        self.assertFalse((self.root / "new.md").exists())
