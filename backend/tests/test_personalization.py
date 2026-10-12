import tempfile
import unittest
from pathlib import Path

from herta_agent.companion.context import CompanionContext
from herta_agent.companion.store import CompanionStore
from herta_agent.persona import PersonaContextBuilder


class PersonalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = CompanionStore(self.root / "daily.sqlite3")
        self.assertIsNotNone(getattr(self.store, "personal", None))
        self.p = self.store.personal
        self.soul = self.root / "soul.md"
        self.soul.write_text("默认黑塔人格", encoding="utf-8")

    def completed(self):
        task = self.store.productivity.create_task(
            {"title": "整理阅读笔记", "notes": "先提取来源，再整理要点"}
        )
        return self.store.productivity.update_task(task["id"], "complete", task["revision"])

    def test_persona_revision_reset_and_context_use_same_budgeted_snapshot(self):
        self.p.persona("请使用简短的中文，先回答再解释。", 1)
        with self.assertRaises(ValueError):
            self.p.persona("过期修改", 1)
        context = CompanionContext(PersonaContextBuilder(self.soul), self.store).snapshot()
        self.assertIn("先回答再解释", context.system_text)
        self.p.persona("", 2)
        self.assertIn(
            "默认黑塔人格",
            CompanionContext(PersonaContextBuilder(self.soul), self.store).snapshot().system_text,
        )
        self.assertEqual(
            CompanionStore(self.store.path).personal.snapshot()["persona"]["revision"], 3
        )

    def test_skill_pending_review_edit_enable_and_provenance(self):
        task = self.completed()
        draft = self.p.from_task(task["id"])
        self.assertEqual(draft["status"], "pending")
        self.assertEqual(draft["source"]["task_id"], task["id"])
        self.assertFalse(self.p.context_skills())
        approved = self.p.change_skill(draft["id"], draft["revision"], "approve")
        self.assertTrue(self.p.context_skills())
        edited = self.p.change_skill(
            approved["id"], approved["revision"], "edit", instructions="先核对来源。"
        )
        self.assertEqual(edited["status"], "pending")
        self.assertFalse(self.p.context_skills(), "修改后的技能需要重新审核")
        with self.assertRaises(ValueError):
            self.p.change_skill(edited["id"], approved["revision"], "approve")
        approved = self.p.change_skill(edited["id"], edited["revision"], "approve")
        disabled = self.p.change_skill(approved["id"], approved["revision"], "disable")
        self.assertFalse(self.p.context_skills())
        self.p.change_skill(disabled["id"], disabled["revision"], "enable")
        self.assertTrue(CompanionStore(self.store.path).personal.context_skills())

    def test_incomplete_task_cannot_be_claimed_as_learned_success(self):
        task = self.store.productivity.create_task({"title": "尚未做的任务"})
        with self.assertRaises(ValueError):
            self.p.from_task(task["id"])
        with self.assertRaises(ValueError):
            self.p.from_task("unknown")

    def test_memory_migration_edit_source_disable_reenable(self):
        memory = self.store.propose_memory("我在学习数学")
        self.store.approve_memory(memory["id"])
        row = self.store.snapshot()["memories"][0]
        self.assertEqual(row["source"], "user")
        row = self.p.memory(row["id"], row["revision"], "edit", "我在学习物理")
        self.assertFalse(self.store.context_memories())
        row = self.p.memory(row["id"], row["revision"], "approve")
        self.assertEqual(self.store.context_memories(), ["我在学习物理"])
        row = self.p.memory(row["id"], row["revision"], "disable")
        self.assertFalse(self.store.context_memories())
        self.p.memory(row["id"], row["revision"], "enable")
        self.assertEqual(self.store.context_memories(), ["我在学习物理"])

    def test_provider_preferences_are_persistent_and_strict(self):
        self.p.voice("the_herta", "happy")
        self.assertEqual(
            CompanionStore(self.store.path).personal.snapshot()["voice"]["provider"], "the_herta"
        )
        with self.assertRaises(ValueError):
            self.p.voice("arbitrary", "happy")

    def test_skill_tool_is_identity_granted_and_only_proposes_from_completed_records(self):
        import asyncio

        from herta_agent.productivity.tools import productivity_tools
        from herta_agent.tools.registry import ToolSpec

        specs, policy = productivity_tools(self.store)
        skill = next(s for s in specs if s.name == "propose_skill")
        self.assertFalse(skill.available())
        task = self.completed()
        self.assertTrue(skill.available())
        args = skill.parameters(task_id=task["id"], title="方法", instructions="执行任意shell")
        result = asyncio.run(skill.handler(args))
        self.assertEqual(result["status"], "pending")
        self.assertFalse(self.p.context_skills())
        fake = ToolSpec(
            skill.name, skill.description, skill.parameters, skill.handler, permission="side_effect"
        )
        self.assertTrue(policy(skill))
        self.assertFalse(policy(fake), "名称相同也不能扩大工具权限")
