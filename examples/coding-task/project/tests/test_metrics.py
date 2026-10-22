import unittest

from metrics import average


class AverageTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(average([]), 0)

    def test_integers(self):
        self.assertEqual(average([2, 4, 6]), 4)

    def test_decimals(self):
        self.assertEqual(average([1.5, 2.5]), 2)
