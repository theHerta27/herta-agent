import unittest
import subject

class Regression(unittest.TestCase):
    def test_regression(self):
        self.assertEqual(subject.average([]), 0)
