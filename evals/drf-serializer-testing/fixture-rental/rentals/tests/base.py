from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from rentals.models import Booking, Branch, Company, Equipment


class RentalsTestCase(TestCase):
    """Base for all rentals tests: fixture builders and the serializer request context."""

    def setup_company(self, name="Acme"):
        return Company.objects.create(name=name)

    def setup_branch(self, company, name="Main"):
        return Branch.objects.create(company=company, name=name)

    def setup_user(self, username="agent"):
        return get_user_model().objects.create_user(username=username)

    def setup_equipment(self, branch, code="DRILL-1", daily_rate=Decimal("20.00"), **fields):
        return Equipment.objects.create(branch=branch, code=code, name=fields.pop("name", code.title()), daily_rate=daily_rate, **fields)

    def setup_booking(self, equipment, user, start, days=1, **fields):
        fields.setdefault("customer_email", "c@example.com")
        return Booking.objects.create(equipment=equipment, booked_by=user, start=start, end=start + timedelta(days=days), **fields)

    def serializer_context(self, company, user):
        """The context the API passes to serializers: a request carrying the user and their company."""
        return {"request": SimpleNamespace(user=user, company=company)}
