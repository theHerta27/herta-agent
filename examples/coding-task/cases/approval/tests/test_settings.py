import unittest

import settings


class SettingsTests(unittest.TestCase):
    def test_settings(self):
        self.assertIsInstance(settings.DEFAULT_RETRIES, int)
        self.assertTrue(settings.ENABLE_LOGGING)
