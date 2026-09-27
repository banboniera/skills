from django.conf import settings
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=100)


class Customer(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=100)


class Product(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="products")
    sku = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "sku"], name="unique_sku_per_company")]


class Order(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"
        PLACED = "placed"
        CANCELLED = "cancelled"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="orders")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    placed_at = models.DateTimeField(null=True, blank=True)


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
