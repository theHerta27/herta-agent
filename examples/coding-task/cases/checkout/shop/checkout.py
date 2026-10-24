from shop.cart import subtotal
from shop.shipping import shipping_fee


def checkout(items, discount_percent=0):
    gross = subtotal(items)
    discount = gross * discount_percent // 100
    shipping = shipping_fee(gross)
    return {
        "subtotal": gross,
        "discount": discount,
        "shipping": shipping,
        "total": gross - discount + shipping,
    }
