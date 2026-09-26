from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from orders.models import Company, Customer, Order, OrderLine, Product


class OrdersTestCase(TestCase):
    """Base for all orders tests: fixture builders and the serializer request context."""

    def setup_company(self, name="Acme"):
        return Company.objects.create(name=name)

    def setup_user(self, username="clerk"):
        return get_user_model().objects.create_user(username=username)

    def setup_customer(self, company, name="Ada"):
        return Customer.objects.create(company=company, name=name)

    def setup_product(self, company, sku="SKU-1", price=Decimal("10.00"), **fields):
        return Product.objects.create(company=company, sku=sku, name=fields.pop("name", sku), price=price, **fields)

    def setup_order(self, company, customer, lines=(), **fields):
        """Create an order; `lines` is a sequence of (product, quantity) pairs priced at the product's price."""
        order = Order.objects.create(company=company, customer=customer, **fields)
        for product, quantity in lines:
            OrderLine.objects.create(order=order, product=product, quantity=quantity, unit_price=product.price)
        return order

    def serializer_context(self, company, user=None):
        """The context the API passes to serializers: a request carrying the user and their company."""
        return {"request": SimpleNamespace(user=user, company=company)}
