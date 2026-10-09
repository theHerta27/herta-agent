import os
import unittest
from unittest.mock import patch

from herta_agent.config import ProviderSettings
from herta_agent.runtime.errors import AgentError


class CredentialAliasTests(unittest.TestCase):
    def test_deepseek_alias_is_used_without_key_in_public_serialization(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fixture-private"}, clear=True):
            settings = ProviderSettings.from_env()
        self.assertEqual(settings.base_url, "https://api.deepseek.com")
        self.assertEqual(settings.model, "deepseek-flash")
        self.assertEqual(settings.api_key.get_secret_value(), "fixture-private")
        self.assertNotIn("fixture-private", repr(settings))
        self.assertNotIn("fixture-private", settings.model_dump_json())

    def test_explicit_herta_overrides_alias_and_empty_key_does_not_fallback(self):
        with patch.dict(
            os.environ,
            {
                "HERTA_BASE_URL": "http://127.0.0.1:8080/v1",
                "HERTA_MODEL": "local-model",
                "HERTA_API_KEY": "local",
                "DEEPSEEK_API_KEY": "private",
            },
            clear=True,
        ):
            settings = ProviderSettings.from_env()
        self.assertEqual(settings.model, "local-model")
        self.assertEqual(settings.api_key.get_secret_value(), "local")
        with (
            patch.dict(
                os.environ, {"HERTA_API_KEY": "", "DEEPSEEK_API_KEY": "private"}, clear=True
            ),
            self.assertRaises(AgentError),
        ):
            ProviderSettings.from_env()
