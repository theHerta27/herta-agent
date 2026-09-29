import unittest
import subject

class Regression(unittest.TestCase):
    def test_regression(self):
        subject.append(1)
        self.assertEqual(subject.append(2), [2])
