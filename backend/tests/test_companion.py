import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from herta_agent.companion.context import CompanionContext
from herta_agent.companion.store import CompanionStore
from herta_agent.companion.tools import companion_tools
from herta_agent.runtime.context import StaticContextBuilder
from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolParameters, ToolRegistry, ToolSpec


class CompanionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "中文陪伴.sqlite3"
        self.store = CompanionStore(self.path)
        self.now = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)

    def tearDown(self):
        self.temp.cleanup()

    def test_reminder_is_persistent_and_each_occurrence_is_unique(self):
        reminder = self.store.create_reminder("喝水", self.now.isoformat(), "once")
        other = CompanionStore(self.path)
        self.store.tick(self.now)
        other.tick(self.now + timedelta(seconds=5))
        deliveries = other.snapshot()["deliveries"]
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0]["reminder_id"], reminder["id"])
        self.assertEqual(deliveries[0]["title"], "喝水")
        other.mark_notified(deliveries[0]["id"])
        self.assertEqual(len(self.store.snapshot()["deliveries"]), 1)
        self.assertTrue(self.store.snapshot()["deliveries"][0]["notified"])
        self.assertFalse(other.snapshot()["reminders"][0]["enabled"])
        other.acknowledge(deliveries[0]["id"])
        self.assertEqual(self.store.snapshot()["deliveries"], [])

    def test_repeating_reminder_after_sleep_delivers_once_and_advances(self):
        self.store.create_reminder("复习", self.now.isoformat(), "daily")
        self.store.tick(self.now + timedelta(days=3, hours=1))
        snapshot = self.store.snapshot()
        self.assertEqual(len(snapshot["deliveries"]), 1)
        self.assertEqual(snapshot["reminders"][0]["due_at"], "2026-10-15T12:00:00+00:00")
        self.store.tick(self.now + timedelta(days=3, hours=2))
        self.assertEqual(len(self.store.snapshot()["deliveries"]), 1)

    def test_cancel_prevents_delivery_and_snooze_reactivates(self):
        reminder = self.store.create_reminder("休息", self.now.isoformat(), "once")
        self.store.cancel_reminder(reminder["id"])
        self.store.tick(self.now)
        self.assertEqual(self.store.snapshot()["deliveries"], [])
        self.store.snooze(reminder["id"], 10, now=self.now)
        self.store.tick(self.now + timedelta(minutes=10))
        self.assertEqual(len(self.store.snapshot()["deliveries"]), 1)

    def test_snoozing_a_daily_delivery_preserves_tomorrows_schedule(self):
        reminder = self.store.create_reminder("喝水", self.now.isoformat(), "daily")
        self.store.tick(self.now)
        tomorrow = (self.now + timedelta(days=1)).isoformat()
        self.store.snooze(reminder["id"], 10, now=self.now)
        self.assertEqual(self.store.snapshot()["deliveries"], [])
        original = next(r for r in self.store.snapshot()["reminders"] if r["id"] == reminder["id"])
        self.assertEqual(original["due_at"], tomorrow)
        self.store.tick(self.now + timedelta(minutes=10))
        self.assertEqual(len(self.store.snapshot()["deliveries"]), 1)
        self.store.tick(self.now + timedelta(minutes=11))
        self.assertEqual(len(self.store.snapshot()["deliveries"]), 1)
        self.store.tick(self.now + timedelta(days=1))
        self.assertEqual(len(self.store.snapshot()["deliveries"]), 2)

    def test_naive_time_and_unknown_repeat_are_rejected(self):
        for date, repeat in [("2026-10-11T12:00", "once"), (self.now.isoformat(), "hourly")]:
            with self.assertRaises(ValueError):
                self.store.create_reminder("提醒", date, repeat)

    def test_cancelled_history_does_not_hide_new_active_reminders(self):
        for _ in range(200):
            reminder = self.store.create_reminder("旧提醒", self.now.isoformat(), "once")
            self.store.cancel_reminder(reminder["id"])
        self.store.create_reminder("新提醒", (self.now + timedelta(days=1)).isoformat(), "once")
        self.assertTrue(any(r["title"] == "新提醒" for r in self.store.snapshot()["reminders"]))

    def test_context_includes_shanghai_time_without_system_timezone_database(self):
        self.store.update_preferences({"nickname": "开拓者"})
        snapshot = CompanionContext(StaticContextBuilder("完整人格"), self.store).snapshot()
        self.assertTrue(snapshot.system_text.startswith("完整人格"))
        self.assertIn("+08:00", snapshot.system_text)
        self.assertIn("开拓者", snapshot.system_text)

    def test_preferences_and_user_approved_memories_survive_restart(self):
        self.store.update_preferences({"nickname": "开拓者"})
        memory = self.store.propose_memory("学习时喜欢先看总结")
        self.assertEqual(self.store.context_memories(), [])
        self.store.approve_memory(memory["id"])
        other = CompanionStore(self.path)
        self.assertEqual(other.snapshot()["preferences"]["nickname"], "开拓者")
        self.assertEqual(other.context_memories(), ["学习时喜欢先看总结"])
        other.delete_memory(memory["id"])
        self.assertEqual(self.store.context_memories(), [])
        with self.assertRaises(ValueError):
            self.store.update_preferences({"api_key": "never-store-this"})


class CompanionPermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_revoking_during_started_notification_prevents_the_handler(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CompanionStore(Path(folder) / "state.db")
            specs, policy = companion_tools(store)
            registry = ToolRegistry()
            for spec in specs:
                registry.register(spec)

            async def on_started():
                store.update_preferences({"allow_tools": False})

            result = await ToolExecutor(registry, tool_policy=policy).execute(
                ToolCall(
                    id="r", name="create_reminder", arguments='{"title":"喝水","delay_minutes":5}'
                ),
                on_started=on_started,
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.error.code, "permission_denied")
            self.assertEqual(store.snapshot()["reminders"], [])

    async def test_only_registered_companion_actions_are_granted_and_revocable(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CompanionStore(Path(folder) / "state.db")
            specs, policy = companion_tools(store)
            registry = ToolRegistry()
            for spec in specs:
                registry.register(spec)

            async def unsafe(_):
                self.fail("generic side effect must never execute")

            registry.register(
                ToolSpec("unsafe", "Unsafe", ToolParameters, unsafe, permission="side_effect")
            )
            executor = ToolExecutor(registry, tool_policy=policy)
            denied = await executor.execute(ToolCall(id="x", name="unsafe", arguments="{}"))
            self.assertEqual(denied.error.code, "permission_denied")
            call = ToolCall(
                id="r", name="create_reminder", arguments='{"title":"喝水","delay_minutes":25}'
            )
            result = await executor.execute(call)
            self.assertTrue(result.ok)
            self.assertEqual(len(store.snapshot()["reminders"]), 1)
            store.update_preferences({"allow_tools": False})
            result = await executor.execute(call)
            self.assertEqual(result.error.code, "permission_denied")
            self.assertEqual(len(store.snapshot()["reminders"]), 1)


if __name__ == "__main__":
    unittest.main()
