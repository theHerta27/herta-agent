"""Amounts use integer cents."""


def subtotal(items):
    return sum(item["unit_cents"] for item in items)
