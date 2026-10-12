import os
import unittest
from unittest.mock import patch

from herta_agent.config import ProviderSettings
from herta_agent.runtime.errors import AgentError


class ProviderEnvironmentTests(unittest.TestCase):
    def test_deepseek_uses_user_requested_provider_key_first(self):
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "deepseek-fixture", "HERTA_API_KEY": "generic-fixture"},
            clear=True,
        ):
            value = ProviderSettings.from_env()
            self.assertEqual(value.api_key.get_secret_value(), "deepseek-fixture")
            self.assertNotIn("deepseek-fixture", repr(value))

    def test_other_provider_never_receives_the_deepseek_key_as_a_fallback(self):
        with patch.dict(
            os.environ,
            {"HERTA_BASE_URL": "http://127.0.0.1:8765", "DEEPSEEK_API_KEY": "deepseek-fixture"},
            clear=True,
        ):
            with self.assertRaises(AgentError):
                ProviderSettings.from_env()
            os.environ["HERTA_API_KEY"] = "local-fixture"
            self.assertEqual(
                ProviderSettings.from_env().api_key.get_secret_value(), "local-fixture"
            )
