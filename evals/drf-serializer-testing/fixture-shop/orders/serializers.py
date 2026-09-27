from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from orders.models import Customer, Order, OrderLine, Product


class CompanyContextMixin:
    """Serializers used by the API get the request in context; `request.company` is the caller's company."""

    @property
    def company(self):
        return self.context["request"].company


class ProductSerializer(CompanyContextMixin, serializers.ModelSerializer):
    """A company's product. The company comes from the request, never from input.

    SKUs are stored trimmed and uppercase and are unique within a company, so a clash is a validation
    error on `sku`, never a database error. Prices are at least 0.01.
    """

    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = Product
        fields = ["id", "sku", "name", "price", "is_active"]

    def validate_sku(self, value):
        sku = value.strip().upper()
        if Product.objects.filter(company=self.company, sku=sku).exists():
            raise serializers.ValidationError("A product with this SKU already exists.", code="duplicate_sku")
        return sku

    def create(self, validated_data):
        return Product.objects.create(company=self.company, **validated_data)


class OrderLineSerializer(serializers.ModelSerializer):
    """One line of an order. `id` identifies an existing line on update; the unit price is copied from the product
    whenever a line is created or its product changes."""

    id = serializers.IntegerField(required=False)
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    quantity = serializers.IntegerField(min_value=1, max_value=999)

    class Meta:
        model = OrderLine
        fields = ["id", "product", "quantity", "unit_price"]
        read_only_fields = ["unit_price"]


class OrderSerializer(CompanyContextMixin, serializers.ModelSerializer):
    """Create and edit orders for the request's company.

    - The customer and every line's product must belong to the request's company; products must be active.
    - The discount is between 0 and 50 percent inclusive.
    - An order can be placed only with at least one line; placing it stamps `placed_at`.
    - Cancelled orders cannot be changed.
    - On update, `lines` is the full new set: lines with an `id` are updated, lines without one are added,
      and existing lines missing from the payload are deleted. Leaving `lines` out keeps the lines as they are.
    - `note` is internal: accepted on input, never returned.
    - `total` is the sum of the lines after the discount, rounded half up to cents.
    """

    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())
    lines = OrderLineSerializer(many=True, required=False)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "customer", "status", "discount_percent", "note", "lines", "total", "created_by", "placed_at"]
        read_only_fields = ["created_by", "placed_at"]
        extra_kwargs = {"note": {"write_only": True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            self.fields["customer"].queryset = Customer.objects.filter(company=self.company)
            self.fields["lines"].child.fields["product"].queryset = Product.objects.filter(is_active=True)

    def validate_discount_percent(self, value):
        if value < 0 or value > 50:
            raise serializers.ValidationError("Discount must be between 0 and 50 percent.", code="discount_range")
        return value

    def validate(self, attrs):
        if self.instance and self.instance.status == Order.Status.CANCELLED:
            raise serializers.ValidationError("Cancelled orders cannot be changed.", code="cancelled")
        status = attrs.get("status", self.instance.status if self.instance else Order.Status.DRAFT)
        if "lines" in attrs:
            has_lines = bool(attrs["lines"])
        else:
            has_lines = bool(self.instance and self.instance.lines.exists())
        if status == Order.Status.PLACED and not has_lines:
            raise serializers.ValidationError({"lines": "An order needs at least one line to be placed."}, code="no_lines")
        return attrs

    def get_total(self, order):
        subtotal = sum((line.quantity * line.unit_price for line in order.lines.all()), Decimal("0"))
        total = subtotal * (100 - order.discount_percent) / 100
        return str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _stamp_placed(self, order, previous_status):
        if order.status == Order.Status.PLACED and previous_status != Order.Status.PLACED:
            order.placed_at = timezone.now()

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        order = Order(company=self.company, created_by=self.context["request"].user, **validated_data)
        self._stamp_placed(order, None)
        order.save()
        for line in lines:
            line.pop("id", None)
            OrderLine.objects.create(order=order, unit_price=line["product"].price, **line)
        return order

    @transaction.atomic
    def update(self, order, validated_data):
        lines = validated_data.pop("lines", [])
        previous_status = order.status
        for attr, value in validated_data.items():
            setattr(order, attr, value)
        self._stamp_placed(order, previous_status)
        order.save()
        existing = {line.pk: line for line in order.lines.all()}
        kept = set()
        for line in lines:
            line_id = line.pop("id", None)
            if line_id in existing:
                current = existing[line_id]
                if current.product_id != line["product"].pk:
                    current.product = line["product"]
                    current.unit_price = line["product"].price
                current.quantity = line["quantity"]
                current.save()
                kept.add(line_id)
            else:
                OrderLine.objects.create(order=order, unit_price=line["product"].price, **line)
        order.lines.filter(pk__in=set(existing) - kept).delete()
        return order


class OrderListSerializer(serializers.ModelSerializer):
    """Compact order rows for list screens. Callers pass orders with `customer` selected and `lines` prefetched,
    and this serializer then runs no queries of its own."""

    customer_name = serializers.CharField(source="customer.name", read_only=True)
    line_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "customer_name", "status", "line_count", "placed_at"]

    def get_line_count(self, order):
        return len(order.lines.all())
