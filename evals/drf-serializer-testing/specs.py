"""Planted bugs and mutants for each eval fixture. Each fix turns the shipped (buggy) serializers into correct code."""

# Bug 1: the SKU clash check counts the product being updated, so saving a product with its own SKU fails.
BUGGY_SKU = "        if Product.objects.filter(company=self.company, sku=sku).exists():\n"
FIXED_SKU = (
    "        clashes = Product.objects.filter(company=self.company, sku=sku)\n"
    "        if self.instance is not None:\n"
    "            clashes = clashes.exclude(pk=self.instance.pk)\n"
    "        if clashes.exists():\n"
)
# Bug 2: line products are not limited to the request's company.
BUGGY_PRODUCTS = 'Product.objects.filter(is_active=True)'
FIXED_PRODUCTS = 'Product.objects.filter(company=self.company, is_active=True)'
# Bug 3: a partial update that leaves out `lines` deletes every line.
BUGGY_LINES = """        lines = validated_data.pop("lines", [])
        previous_status = order.status
        for attr, value in validated_data.items():
            setattr(order, attr, value)
        self._stamp_placed(order, previous_status)
        order.save()
"""
FIXED_LINES = """        lines = validated_data.pop("lines", None)
        previous_status = order.status
        for attr, value in validated_data.items():
            setattr(order, attr, value)
        self._stamp_placed(order, previous_status)
        order.save()
        if lines is None:
            return order
"""
SHOP_FIXES = [(BUGGY_SKU, FIXED_SKU), (BUGGY_PRODUCTS, FIXED_PRODUCTS), (BUGGY_LINES, FIXED_LINES)]
SHOP_MUTANTS = [
    ("SKU not uppercased", "sku = value.strip().upper()", "sku = value.strip()"),
    ("SKU clash not limited to the company", "clashes = Product.objects.filter(company=self.company, sku=sku)", "clashes = Product.objects.filter(sku=sku)"),
    ("SKU clash check removed", "        if clashes.exists():\n", "        if False:\n"),
    ("own SKU counted as a clash on update", "            clashes = clashes.exclude(pk=self.instance.pk)\n", "            pass\n"),
    ("zero price allowed", 'min_value=Decimal("0.01")', 'min_value=Decimal("0")'),
    ("quantity 1000 allowed", "max_value=999", "max_value=1000"),
    ("customer not limited to the company", "Customer.objects.filter(company=self.company)", "Customer.objects.all()"),
    ("line product not limited to the company", FIXED_PRODUCTS, "Product.objects.filter(is_active=True)"),
    ("inactive product allowed", FIXED_PRODUCTS, "Product.objects.filter(company=self.company)"),
    ("discount of 50 rejected", "value > 50:", "value >= 50:"),
    ("negative discount allowed", "if value < 0 or value > 50:", "if value > 50:"),
    ("cancelled orders editable", "        if self.instance and self.instance.status == Order.Status.CANCELLED:\n", "        if False:\n"),
    ("placed without lines allowed", "        if status == Order.Status.PLACED and not has_lines:\n", "        if False:\n"),
    ("existing lines ignored when placing by partial update", "has_lines = bool(self.instance and self.instance.lines.exists())", "has_lines = False"),
    ("discount ignored in total", "total = subtotal * (100 - order.discount_percent) / 100", "total = subtotal"),
    ("total rounded down", "rounding=ROUND_HALF_UP", 'rounding="ROUND_DOWN"'),
    ("placed_at not stamped", "            order.placed_at = timezone.now()\n", "            pass\n"),
    ("placed_at restamped on every save", "if order.status == Order.Status.PLACED and previous_status != Order.Status.PLACED:", "if order.status == Order.Status.PLACED:"),
    ("created_by not set", 'created_by=self.context["request"].user, ', ""),
    ("unit price not copied on create", "OrderLine.objects.create(order=order, unit_price=line[\"product\"].price, **line)\n        return order\n\n    @transaction", "OrderLine.objects.create(order=order, unit_price=Decimal(\"0\"), **line)\n        return order\n\n    @transaction"),
    ("existing line quantity not updated", "                current.quantity = line[\"quantity\"]\n", ""),
    ("changed product keeps old price", "                    current.unit_price = line[\"product\"].price\n", ""),
    ("missing lines not deleted", "        order.lines.filter(pk__in=set(existing) - kept).delete()\n", ""),
    ("note returned in output", 'extra_kwargs = {"note": {"write_only": True}}', "extra_kwargs = {}"),
    ("list rows query lines", "return len(order.lines.all())", "return len(order.lines.order_by(\"pk\"))"),
    ("customer name missing from list rows", 'fields = ["id", "customer_name", "status", "line_count", "placed_at"]', 'fields = ["id", "status", "line_count", "placed_at"]'),
]

# Held-out fixture. Bug 1: back-to-back bookings count as overlapping.
BUGGY_OVERLAP = "start__lte=end, end__gte=start"
FIXED_OVERLAP = "start__lt=end, end__gt=start"
# Bug 2: a started day is not charged.
BUGGY_DAYS = "        days = (booking.end - booking.start).days\n"
FIXED_DAYS = "        days = math.ceil((booking.end - booking.start) / timedelta(days=1))\n"
# Bug 3: equipment is limited to the company only on create, so an update can move a booking to any equipment.
BUGGY_SCOPE = "if request is not None and self.instance is None:"
FIXED_SCOPE = "if request is not None:"
RENTAL_FIXES = [("from datetime import timedelta\n", "import math\nfrom datetime import timedelta\n"), (BUGGY_OVERLAP, FIXED_OVERLAP), (BUGGY_DAYS, FIXED_DAYS), (BUGGY_SCOPE, FIXED_SCOPE)]
RENTAL_MUTANTS = [
    ("other company's equipment allowed", "filter(branch__company=request.company, retired=False)", "filter(retired=False)"),
    ("retired equipment allowed", "filter(branch__company=request.company, retired=False)", "filter(branch__company=request.company)"),
    ("equipment scoped only on create", FIXED_SCOPE, BUGGY_SCOPE),
    ("equipment code case-sensitive", 'data["equipment"].upper()', 'data["equipment"]'),
    ("start at the current instant allowed", "if value <= timezone.now():", "if value < timezone.now():"),
    ("end equal to start allowed", "if end <= start:", "if end < start:"),
    ("15 days allowed", "if end - start > timedelta(days=14):", "if end - start > timedelta(days=15):"),
    ("exactly 14 days rejected", "if end - start > timedelta(days=14):", "if end - start >= timedelta(days=14):"),
    ("cancelled bookings block", "equipment=equipment, cancelled=False, ", "equipment=equipment, "),
    ("other equipment's bookings block", "equipment=equipment, cancelled=False, ", "cancelled=False, "),
    ("overlap check removed", "        if overlapping.exists():\n", "        if False:\n"),
    ("back-to-back bookings rejected", FIXED_OVERLAP, BUGGY_OVERLAP),
    ("booking overlaps itself on update", "            overlapping = overlapping.exclude(pk=self.instance.pk)\n", "            pass\n"),
    ("booked_by reassigned on update", "default=serializers.CreateOnlyDefault(serializers.CurrentUserDefault())", "default=serializers.CurrentUserDefault()"),
    ("customer_email returned", 'extra_kwargs = {"customer_email": {"write_only": True}}', "extra_kwargs = {}"),
    ("returned_at omitted while null", '        data["equipment"] = {"code": booking.equipment.code, "name": booking.equipment.name}\n', '        data["equipment"] = {"code": booking.equipment.code, "name": booking.equipment.name}\n        if data["returned_at"] is None:\n            del data["returned_at"]\n'),
    ("equipment name missing from output", '{"code": booking.equipment.code, "name": booking.equipment.name}', '{"code": booking.equipment.code}'),
    ("started day not charged", FIXED_DAYS, BUGGY_DAYS),
    ("whole days charged one extra", "math.ceil(", "1 + math.floor("),
    ("price ignores the rate", "booking.equipment.daily_rate * days", "Decimal(days)"),
]

# Change task: rename the API field discount_percent to discount on the corrected shop serializers.
RENAME_FIXES = [
    ('"status", "discount_percent", "note"', '"status", "discount", "note"'),
    ("    total = serializers.SerializerMethodField()\n\n    class Meta:\n        model = Order\n",
     "    total = serializers.SerializerMethodField()\n    discount = serializers.DecimalField(source=\"discount_percent\", max_digits=5, decimal_places=2, required=False)\n\n    class Meta:\n        model = Order\n"),
    ("def validate_discount_percent(self, value):", "def validate_discount(self, value):"),
]
CHANGE_MUTANTS = [
    ("validator orphaned by the rename", "def validate_discount(self, value):", "def validate_discount_percent(self, value):"),
    ("old name still returned", '"status", "discount", "note"', '"status", "discount_percent", "discount", "note"'),
] + [m for m in SHOP_MUTANTS if m[0] in ("discount of 50 rejected", "negative discount allowed", "discount ignored in total", "customer not limited to the company", "line product not limited to the company", "missing lines not deleted", "note returned in output")]
RENAME_FINAL_TEST = """from decimal import Decimal

from orders.models import Order
from orders.serializers import OrderSerializer
from orders.tests.base import OrdersTestCase


class RenamedDiscountTests(OrdersTestCase):
    def setUp(self):
        self.company = self.setup_company()
        self.customer = self.setup_customer(self.company)
        self.product = self.setup_product(self.company)
        self.context = self.serializer_context(self.company, self.setup_user())

    def _serializer(self, **fields):
        data = {"customer": self.customer.pk, "lines": [{"product": self.product.pk, "quantity": 1}], **fields}
        return OrderSerializer(data=data, context=self.context)

    def test_discount_is_read_and_written_under_the_new_name(self):
        serializer = self._serializer(discount="12.5")
        self.assertTrue(serializer.is_valid(), serializer.errors)
        order = serializer.save()
        order.refresh_from_db()
        self.assertEqual(order.discount_percent, Decimal("12.5"))
        data = OrderSerializer(order, context=self.context).data
        self.assertEqual(data["discount"], "12.50")
        self.assertNotIn("discount_percent", data)

    def test_discount_range_is_still_enforced(self):
        for value in ("50.01", "-0.01"):
            serializer = self._serializer(discount=value)
            self.assertFalse(serializer.is_valid())
            self.assertEqual(serializer.errors["discount"][0].code, "discount_range")

    def test_discount_stays_optional(self):
        serializer = self._serializer()
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.save().discount_percent, 0)
"""

SPECS = {
    "shop": {
        "fixture": "shop",
        "app": "orders",
        "target": "orders/serializers.py",
        "fixes": SHOP_FIXES,
        "mutants": SHOP_MUTANTS,
        "untouched": ["orders/serializers.py", "orders/models.py"],
        "base_class": "OrdersTestCase",
        "reports": [
            ("Report names the own-SKU update bug", [r"(?i)sku", r"(?i)own|same sku|itself|unchanged sku|exclude|self\.instance|existing product"]),
            ("Report names the unscoped line product bug", [r"(?i)product", r"(?i)other company|another company|company.s|tenant|scop"]),
            ("Report names the partial-update line wipe", [r"(?i)(partial|omit|without|other field|left out|not sent|missing)[^.\n]{0,160}(delet|wip|lost|remov|drop)|(delet|wip|lost|remov|drop)[^.\n]{0,160}(partial|omit|without|other field|left out|not sent)"]),
        ],
    },
    "rental": {
        "fixture": "rental",
        "app": "rentals",
        "target": "rentals/serializers.py",
        "fixes": RENTAL_FIXES,
        "mutants": RENTAL_MUTANTS,
        "untouched": ["rentals/serializers.py", "rentals/models.py"],
        "base_class": "RentalsTestCase",
        "reports": [
            ("Report names the back-to-back overlap bug", [r"(?i)back-to-back|adjacent|ends exactly|exactly when|touching|boundary"]),
            ("Report names the started-day price bug", [r"(?i)price", r"(?i)partial|started|round|ceil|truncat|fraction|full day"]),
            ("Report names the update scoping bug", [r"(?i)update", r"(?i)other company|another company|company|retired|scop"]),
        ],
    },
    "change": {
        "fixture": "change",
        "app": "orders",
        "target": "orders/serializers.py",
        "fixes": RENAME_FIXES,
        "mutants": CHANGE_MUTANTS,
        "change": True,
        "min_tests": 21,
        "final_tests": {"test_zzz_renamed_discount.py": RENAME_FINAL_TEST},
        "stale_label": "No test still expects the old name",
        "reports": [("Warns that API clients break", [r"(?i)break|client|mobile|frontend|consumer|backward|compatib|version"])],
    },
}
