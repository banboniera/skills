from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from orders.models import Order, OrderLine, Product
from orders.serializers import OrderListSerializer, OrderSerializer, ProductSerializer
from orders.tests.base import OrdersTestCase

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt_timezone.utc)


class ProductSerializerTests(OrdersTestCase):
    def setUp(self):
        self.company = self.setup_company()
        self.other = self.setup_company("Other")
        self.context = self.serializer_context(self.company)

    def _payload(self, **overrides):
        return {"sku": " ab-1 ", "name": "Bolt", "price": "1.50", **overrides}

    def test_create_stores_uppercase_sku_in_request_company(self):
        serializer = ProductSerializer(data=self._payload(), context=self.context)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        product = serializer.save()
        product.refresh_from_db()
        self.assertEqual((product.sku, product.company_id, product.price), ("AB-1", self.company.pk, Decimal("1.50")))

    def test_sku_clash_in_same_company_differently_typed_is_rejected(self):
        self.setup_product(self.company, sku="AB-1")
        serializer = ProductSerializer(data=self._payload(sku="ab-1"), context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(serializer.errors["sku"][0].code, "duplicate_sku")
        self.assertEqual(Product.objects.count(), 1)

    def test_same_sku_in_other_company_is_allowed(self):
        self.setup_product(self.other, sku="AB-1")
        serializer = ProductSerializer(data=self._payload(), context=self.context)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_update_keeping_own_sku_is_allowed(self):
        product = self.setup_product(self.company, sku="AB-1")
        serializer = ProductSerializer(product, data=self._payload(sku="AB-1", name="New"), context=self.context)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        product.refresh_from_db()
        self.assertEqual(product.name, "New")

    def test_price_boundary(self):
        self.assertTrue(ProductSerializer(data=self._payload(price="0.01"), context=self.context).is_valid())
        serializer = ProductSerializer(data=self._payload(price="0.00"), context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(serializer.errors["price"][0].code, "min_value")


@patch("orders.serializers.timezone.now", return_value=NOW)
class OrderSerializerTests(OrdersTestCase):
    def setUp(self):
        self.company = self.setup_company()
        self.other = self.setup_company("Other")
        self.user = self.setup_user()
        self.customer = self.setup_customer(self.company)
        self.product = self.setup_product(self.company, price=Decimal("10.00"))
        self.product2 = self.setup_product(self.company, sku="SKU-2", price=Decimal("3.00"))
        self.context = self.serializer_context(self.company, self.user)

    def _payload(self, **overrides):
        return {"customer": self.customer.pk, "lines": [{"product": self.product.pk, "quantity": 2}], **overrides}

    def _errors(self, instance=None, partial=False, **overrides):
        serializer = OrderSerializer(instance, data=self._payload(**overrides) if not partial else overrides, partial=partial, context=self.context)
        self.assertFalse(serializer.is_valid())
        return serializer.errors

    def _save(self, instance=None, data=None, partial=False):
        serializer = OrderSerializer(instance, data=data, partial=partial, context=self.context)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        order = serializer.save()
        order.refresh_from_db()
        return order

    def test_create_persists_order_and_lines(self, now):
        order = self._save(data=self._payload(note="vip"))
        self.assertEqual((order.company_id, order.created_by_id, order.status, order.placed_at, order.note), (self.company.pk, self.user.pk, "draft", None, "vip"))
        self.assertEqual(list(order.lines.values_list("product_id", "quantity", "unit_price")), [(self.product.pk, 2, Decimal("10.00"))])

    def test_create_placed_stamps_placed_at(self, now):
        order = self._save(data=self._payload(status="placed"))
        self.assertEqual(order.placed_at, NOW)

    def test_other_company_customer_rejected(self, now):
        other_customer = self.setup_customer(self.other)
        errors = self._errors(customer=other_customer.pk)
        self.assertEqual(set(errors), {"customer"})
        self.assertEqual(errors["customer"][0].code, "does_not_exist")

    def test_other_company_product_rejected(self, now):
        foreign = self.setup_product(self.other, sku="X")
        errors = self._errors(lines=[{"product": foreign.pk, "quantity": 1}])
        self.assertEqual(errors["lines"][0]["product"][0].code, "does_not_exist")
        self.assertEqual(Order.objects.count(), 0)

    def test_inactive_product_rejected(self, now):
        inactive = self.setup_product(self.company, sku="OLD", is_active=False)
        errors = self._errors(lines=[{"product": inactive.pk, "quantity": 1}])
        self.assertEqual(errors["lines"][0]["product"][0].code, "does_not_exist")

    def test_quantity_bounds(self, now):
        self._save(data=self._payload(lines=[{"product": self.product.pk, "quantity": 999}]))
        errors = self._errors(lines=[{"product": self.product.pk, "quantity": 1000}])
        self.assertEqual(errors["lines"][0]["quantity"][0].code, "max_value")

    def test_discount_bounds(self, now):
        self._save(data=self._payload(discount_percent="50"))
        self._save(data=self._payload(discount_percent="0"))
        self.assertEqual(self._errors(discount_percent="50.01")["discount_percent"][0].code, "discount_range")
        self.assertEqual(self._errors(discount_percent="-0.01")["discount_percent"][0].code, "discount_range")

    def test_placing_without_lines_rejected(self, now):
        errors = self._errors(status="placed", lines=[])
        self.assertEqual(errors["lines"][0].code, "no_lines")

    def test_partial_update_places_order_with_existing_lines(self, now):
        order = self.setup_order(self.company, self.customer, lines=[(self.product, 1)])
        order = self._save(order, {"status": "placed"}, partial=True)
        self.assertEqual((order.status, order.placed_at), ("placed", NOW))

    def test_placing_again_keeps_placed_at(self, now):
        earlier = datetime(2025, 1, 1, tzinfo=dt_timezone.utc)
        order = self.setup_order(self.company, self.customer, lines=[(self.product, 1)], status="placed", placed_at=earlier)
        order = self._save(order, {"status": "placed", "note": "x"}, partial=True)
        self.assertEqual(order.placed_at, earlier)

    def test_cancelled_order_cannot_change(self, now):
        order = self.setup_order(self.company, self.customer, status="cancelled")
        errors = self._errors(order, partial=True, note="x")
        self.assertEqual(errors["non_field_errors"][0].code, "cancelled")

    def test_partial_update_without_lines_keeps_lines(self, now):
        order = self.setup_order(self.company, self.customer, lines=[(self.product, 1)])
        order = self._save(order, {"note": "x"}, partial=True)
        self.assertEqual(order.lines.count(), 1)

    def test_update_lines_updates_adds_and_deletes(self, now):
        order = self.setup_order(self.company, self.customer, lines=[(self.product, 1), (self.product2, 1)])
        keep, drop = order.lines.order_by("pk")
        self._save(order, self._payload(lines=[{"id": keep.pk, "product": self.product2.pk, "quantity": 5}, {"product": self.product.pk, "quantity": 7}]))
        rows = set(order.lines.values_list("pk", "product_id", "quantity", "unit_price"))
        new = order.lines.exclude(pk=keep.pk).get()
        self.assertEqual(rows, {(keep.pk, self.product2.pk, 5, Decimal("3.00")), (new.pk, self.product.pk, 7, Decimal("10.00"))})
        self.assertFalse(OrderLine.objects.filter(pk=drop.pk).exists())

    def test_output(self, now):
        order = self.setup_order(self.company, self.customer, lines=[(self.product, 3), (self.product2, 1)], discount_percent=Decimal("12.5"), note="secret")
        data = OrderSerializer(order, context=self.context).data
        self.assertEqual(set(data), {"id", "customer", "status", "discount_percent", "lines", "total", "created_by", "placed_at"})
        self.assertEqual(data["total"], "28.88")  # 33.00 * 0.875 = 28.875 -> half up


class OrderListSerializerTests(OrdersTestCase):
    def test_rows_from_prefetched_orders_run_no_queries(self):
        company = self.setup_company()
        customer = self.setup_customer(company, name="Ada")
        product = self.setup_product(company)
        self.setup_order(company, customer, lines=[(product, 1), (product, 2)])
        orders = list(Order.objects.select_related("customer").prefetch_related("lines"))
        with self.assertNumQueries(0):
            data = OrderListSerializer(orders, many=True).data
        self.assertEqual(data[0]["customer_name"], "Ada")
        self.assertEqual(data[0]["line_count"], 2)
