import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from herta_agent.companion.store import CompanionStore


class ProductivityTests(unittest.TestCase):
    def test_reopened_delivered_task_creates_new_occurrence_without_losing_history(self):
        task = self.task()
        self.daily.tick(self.due)
        done = self.p.update_task(task["id"], "complete", task["revision"], now=self.due)
        reopened = self.p.update_task(task["id"], "reopen", done["revision"], now=self.due)
        self.daily.tick(self.due + timedelta(seconds=1))
        with self.daily.connection() as db:
            deliveries = [dict(r) for r in db.execute("SELECT * FROM deliveries")]
        self.assertEqual(len(deliveries), 2)
        self.assertEqual(sum(not r["acknowledged"] for r in deliveries), 1)
        self.assertNotEqual(reopened["reminder_id"], task["reminder_id"])
        self.assertEqual(len(self.p.history(task["id"])), 2)

    def test_recurring_snooze_follows_task_completion_cancel_and_postpone(self):
        for action in ("complete", "cancel", "postpone", "edit"):
            with self.subTest(action=action):
                task = self.task(repeat="daily")
                self.daily.tick(self.due)
                self.daily.snooze(task["reminder_id"], 10, now=self.due)
                values = (
                    {"due_at": (self.due + timedelta(days=2)).isoformat()}
                    if action in {"postpone", "edit"}
                    else {}
                )
                updated = self.p.update_task(
                    task["id"], action, task["revision"], now=self.due, **values
                )
                self.daily.tick(self.due + timedelta(minutes=11))
                with self.daily.connection() as db:
                    active = db.execute(
                        "SELECT COUNT(*) FROM deliveries WHERE acknowledged=0"
                    ).fetchone()[0]
                    original = db.execute(
                        "SELECT * FROM reminders WHERE id=?", (task["reminder_id"],)
                    ).fetchone()
                self.assertEqual(active, 0, "完成、取消或改期后不能再响本次稍后提醒")
                self.assertEqual(bool(original["enabled"]), action != "cancel")
                self.assertEqual(original["due_at"], updated["due_at"])
                self.p.update_task(task["id"], "cancel", updated["revision"], now=self.due)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Herta 学习任务 ")
        self.addCleanup(self.temp.cleanup)
        self.daily = CompanionStore(Path(self.temp.name) / "companionship.sqlite3")
        self.assertIsNotNone(getattr(self.daily, "productivity", None), "学习任务工作区尚未实现")
        self.p = self.daily.productivity
        self.now = datetime(2026, 10, 12, 12, tzinfo=UTC)
        self.due = self.now + timedelta(hours=1)

    def task(self, **options):
        return self.p.create_task(
            {
                "title": "学习量子计算",
                "due_at": self.due.isoformat(),
                "repeat": "once",
                "remind": True,
                **options,
            },
            now=self.now,
        )

    def test_task_and_reminder_are_persistent_and_completion_is_idempotent(self):
        task = self.task(request_id="first")
        duplicate = self.task(request_id="first")
        self.assertEqual(task["id"], duplicate["id"])
        self.assertEqual(len(self.daily.snapshot()["reminders"]), 1)
        reopened = CompanionStore(self.daily.path).productivity
        self.assertEqual(reopened.snapshot()["tasks"][0]["title"], task["title"])
        done = self.p.update_task(task["id"], "complete", task["revision"], now=self.now)
        self.assertEqual(done["status"], "completed")
        self.assertFalse(self.daily.snapshot()["reminders"][0]["enabled"])
        with self.assertRaises(ValueError):
            self.p.update_task(task["id"], "complete", task["revision"], now=self.now)
        self.assertEqual(len(self.p.history(task["id"])), 1)

    def test_recurring_completion_advances_from_original_time_and_snooze_syncs(self):
        task = self.task(repeat="daily")
        done = self.p.update_task(
            task["id"], "complete", task["revision"], now=self.now + timedelta(days=3)
        )
        self.assertEqual(done["status"], "open")
        self.assertEqual(done["due_at"], (self.due + timedelta(days=3)).isoformat())
        postponed = self.p.update_task(
            done["id"],
            "postpone",
            done["revision"],
            due_at=(self.now + timedelta(days=5)).isoformat(),
            now=self.now,
        )
        reminder = next(
            r for r in self.daily.snapshot()["reminders"] if r["id"] == task["reminder_id"]
        )
        self.assertEqual(reminder["due_at"], postponed["due_at"])
        cancelled = self.p.update_task(
            postponed["id"], "cancel", postponed["revision"], now=self.now
        )
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertFalse(self.daily.snapshot()["reminders"][0]["enabled"])

    def test_goals_tasks_and_revision_protection(self):
        goal = self.p.create_goal({"title": "理解量子基础", "notes": "循序学习"})
        task = self.task(goal_id=goal["id"])
        self.p.update_task(task["id"], "complete", task["revision"], now=self.now)
        self.assertEqual(self.p.snapshot()["goals"][0]["completed_tasks"], 1)
        self.p.update_goal(goal["id"], "completed", goal["revision"])
        with self.assertRaises(ValueError):
            self.p.update_goal(goal["id"], "active", goal["revision"])

    def test_learning_progress_review_and_roles_are_persistent(self):
        material = self.p.add_material(
            {
                "title": "量子笔记",
                "root_id": "authorized-root",
                "path": "笔记/量子.md",
                "notes": "重点是叠加态",
            },
            now=self.now,
        )
        updated = self.p.update_material(
            material["id"], material["revision"], progress=60, notes="已学习基础", now=self.now
        )
        reviewed = self.p.review(
            material["id"], updated["revision"], now=self.now + timedelta(days=1)
        )
        self.assertEqual(reviewed["review_count"], 1)
        self.assertEqual(len(self.p.review_suggestions(now=self.now + timedelta(days=8))), 1)
        self.p.set_role("tutor")
        self.assertEqual(CompanionStore(self.daily.path).productivity.snapshot()["role"], "tutor")
        with self.assertRaises(ValueError):
            self.p.set_role("shell_executor")
        with self.assertRaises(ValueError):
            self.p.add_material(
                {"title": "越界", "root_id": "root", "path": "../outside"}, now=self.now
            )

    def test_repetition_comparison_marks_omissions_without_claiming_semantic_grade(self):
        result = self.p.compare_recitation("量子比特描述叠加态", "量子描述叠加态")
        self.assertIn("比特", result["missing"])
        self.assertIn("文字", result["note"])

    def test_failed_linked_reminder_transaction_does_not_leave_task(self):
        with self.daily.connection() as db:
            for i in range(200):
                db.execute(
                    "INSERT INTO reminders VALUES(?,?,?,?,1)",
                    (str(i), "已有提醒", self.due.isoformat(), "once"),
                )
        with self.assertRaises(ValueError):
            self.task()
        self.assertFalse(self.p.snapshot()["tasks"])

    def test_daily_reminder_controls_sync_linked_once_task(self):
        task = self.task()
        self.daily.snooze(task["reminder_id"], 10, now=self.now)
        current = self.p.snapshot()["tasks"][0]
        self.assertEqual(current["due_at"], (self.now + timedelta(minutes=10)).isoformat())
        self.assertGreater(current["revision"], task["revision"])
        self.daily.cancel_reminder(task["reminder_id"])
        self.assertFalse(self.p.snapshot()["tasks"][0]["remind"])

    def test_request_id_is_bound_to_creation_payload(self):
        self.task(request_id="same-request")
        with self.assertRaises(ValueError):
            self.task(request_id="same-request", title="另外一个任务")

    def test_task_revision_can_change_date_and_reminder_together(self):
        task = self.task()
        due = self.now + timedelta(days=2)
        changed = self.p.update_task(
            task["id"],
            "edit",
            task["revision"],
            due_at=due.isoformat(),
            title="修改后的任务",
            now=self.now,
        )
        self.assertEqual(changed["due_at"], due.isoformat())
        self.assertEqual(self.daily.snapshot()["reminders"][0]["due_at"], changed["due_at"])

    def test_open_tasks_are_prioritized_and_closed_goals_reject_new_children(self):
        done = self.task()
        self.p.update_task(done["id"], "complete", done["revision"], now=self.now)
        opened = self.task(title="待完成的任务")
        self.assertEqual(self.p.snapshot()["tasks"][0]["id"], opened["id"])
        goal = self.p.create_goal({"title": "已结束目标"})
        self.p.update_goal(goal["id"], "completed", goal["revision"])
        with self.assertRaises(ValueError):
            self.task(goal_id=goal["id"])

    def test_closed_goal_rejects_new_task(self):
        goal = self.p.create_goal({"title": "已完成目标"})
        self.p.update_goal(goal["id"], "completed", goal["revision"])
        with self.assertRaises(ValueError):
            self.task(goal_id=goal["id"])
