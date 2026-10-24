import unittest

from shop.checkout import checkout


class CheckoutTests(unittest.TestCase):
    def test_below_threshold(self):
        self.assertEqual(checkout([{"unit_cents": 2000, "quantity": 1}])["total"], 2500)

    def test_threshold_is_free(self):
        self.assertEqual(checkout([{"unit_cents": 5000, "quantity": 1}])["shipping"], 0)

    def test_threshold_after_discount(self):
        self.assertEqual(
            checkout([{"unit_cents": 5000, "quantity": 1}], 10)["shipping"], 500
        )

    def test_quantity_and_discount(self):
        self.assertEqual(
            checkout([{"unit_cents": 3000, "quantity": 2}], 20),
            {"subtotal": 6000, "discount": 1200, "shipping": 500, "total": 5300},
        )
