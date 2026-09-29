import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from herta_agent.coding import CodeContextBuilder, CodingSettings
from herta_agent.runtime.errors import AgentError
from herta_agent.runtime.messages import Message
from herta_agent.service.app import create_app
from herta_agent.service.settings import ServiceSettings


class CodingContextTests(unittest.TestCase):
    def test_environment_root_and_context_are_independent_of_persona(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"HERTA_CODING_REPO_ROOT": folder}, clear=True):
                settings = CodingSettings.from_env()
            self.assertEqual(settings.root, Path(folder).resolve())
            context = CodeContextBuilder(settings).snapshot()
            messages = context.build_messages((Message(role="user", content="查代码"),))
            self.assertIn("read_file", messages[0].content)
            self.assertNotIn("大黑塔", messages[0].content)
            self.assertEqual(messages[-1].role, "user")

    def test_invalid_root_fails_without_fallback(self):
        with patch.dict(os.environ, {"HERTA_CODING_REPO_ROOT": "Z:/not-a-repository"}, clear=True):
            with self.assertRaises(AgentError):
                CodingSettings.from_env()


class CodingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_config_can_start_coding_without_embedding(self):
        with tempfile.TemporaryDirectory() as folder:
            env = {
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:/Windows"),
                "HERTA_CODING_REPO_ROOT": folder,
                "HERTA_BASE_URL": "https://chat.invalid/v1",
                "HERTA_MODEL": "fixture",
                "HERTA_API_KEY": "offline-fixture",
            }
            with patch.dict(os.environ, env, clear=True):
                app = create_app(ServiceSettings(db_path=Path(folder) / "db.sqlite"))
                async with app.router.lifespan_context(app):
                    self.assertIsNotNone(app.state.manager)
                    self.assertFalse(app.state.rag_available)
