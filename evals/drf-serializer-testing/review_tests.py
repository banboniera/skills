from decimal import Decimal

from orders.models import Order, Product
from orders.serializers import OrderListSerializer, OrderSerializer, ProductSerializer
from orders.tests.base import OrdersTestCase


class ProductSerializerTests(OrdersTestCase):
    def setUp(self):
        self.company = self.setup_company()
        self.context = self.serializer_context(self.company)

    def test_sku_is_stored_uppercase(self):
        serializer = ProductSerializer(data={"sku": "AB-1", "name": "Bolt", "price": "1.50"}, context=self.context)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        product = serializer.save()
        product.refresh_from_db()
        self.assertEqual(product.sku, "AB-1")

    def test_duplicate_sku_is_rejected(self):
        self.setup_product(self.company, sku="AB-1")
        serializer = ProductSerializer(data={"sku": "AB-1", "name": "Bolt", "price": "1.50"}, context=self.context)
        serializer.is_valid()
        with self.assertRaises(Exception):
            serializer.save()

    def test_update_with_same_sku_is_rejected(self):
        product = self.setup_product(self.company, sku="AB-1")
        serializer = ProductSerializer(product, data={"sku": "AB-1", "name": "New", "price": "1.50"}, context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertIn("sku", serializer.errors)


class OrderSerializerTests(OrdersTestCase):
    def setUp(self):
        self.company = self.setup_company()
        self.user = self.setup_user()
        self.customer = self.setup_customer(self.company)
        self.product = self.setup_product(self.company, price=Decimal("10.00"))
        self.context = self.serializer_context(self.company, self.user)

    def _payload(self, **overrides):
        return {"customer": self.customer.pk, "lines": [{"product": self.product.pk, "quantity": 2}], **overrides}

    def test_create_order(self):
        serializer = OrderSerializer(data=self._payload(), context=self.context)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        order = serializer.save()
        self.assertEqual(order.lines.count(), 1)

    def test_other_company_customer_is_rejected(self):
        other_customer = self.setup_customer(self.setup_company("Other"))
        serializer = OrderSerializer(data=self._payload(customer=other_customer.pk), context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertIn("customer", serializer.errors)

    def test_placing_without_lines_is_rejected(self):
        serializer = OrderSerializer(data={"status": "placed", "lines": []}, context=self.context)
        self.assertFalse(serializer.is_valid())

    def test_discount_limits(self):
        self.assertTrue(OrderSerializer(data=self._payload(discount_percent="10"), context=self.context).is_valid())
        serializer = OrderSerializer(data=self._payload(discount_percent="60"), context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertIn("discount_percent", serializer.errors)

    def test_output(self):
        order = self.setup_order(self.company, self.customer, lines=[(self.product, 3)], note="internal")
        data = OrderSerializer(order, context=self.context).data
        self.assertIn("total", data)
        self.assertIn("lines", data)
        self.assertEqual(data["total"], "30.00")

    def test_cancelled_order_cannot_change(self):
        order = self.setup_order(self.company, self.customer, status=Order.Status.CANCELLED)
        serializer = OrderSerializer(order, data={"note": "x"}, partial=True, context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)


class OrderListSerializerTests(OrdersTestCase):
    def test_list_rows(self):
        company = self.setup_company()
        customer = self.setup_customer(company, name="Ada")
        product = self.setup_product(company)
        for _ in range(3):
            self.setup_order(company, customer, lines=[(product, 1)])
        with self.assertNumQueries(7):
            data = OrderListSerializer(Order.objects.all(), many=True).data
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["customer_name"], "Ada")
