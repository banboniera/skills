from django.conf import settings
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=100)


class Branch(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=100)


class Equipment(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="equipment")
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    daily_rate = models.DecimalField(max_digits=8, decimal_places=2)
    retired = models.BooleanField(default=False)


class Booking(models.Model):
    equipment = models.ForeignKey(Equipment, on_delete=models.PROTECT, related_name="bookings")
    booked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    customer_email = models.EmailField()
    start = models.DateTimeField()
    end = models.DateTimeField()
    cancelled = models.BooleanField(default=False)
    returned_at = models.DateTimeField(null=True, blank=True)
