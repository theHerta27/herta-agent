import unittest
import subject

class Regression(unittest.TestCase):
    def test_regression(self):
        self.assertTrue(subject.is_adult(18))
