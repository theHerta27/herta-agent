import unittest

from shop.cart import subtotal


class CartTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(subtotal([]), 0)

    def test_single(self):
        self.assertEqual(subtotal([{"unit_cents": 100, "quantity": 1}]), 100)

    def test_quantity(self):
        self.assertEqual(subtotal([{"unit_cents": 100, "quantity": 3}]), 300)
