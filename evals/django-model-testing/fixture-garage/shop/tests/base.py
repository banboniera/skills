from django.test import TestCase

from shop.models import Vehicle, Workshop


class ShopTestCase(TestCase):
    """Base for shop tests: shared fixture helpers."""

    @classmethod
    def setup_workshop(cls, name: str = "Main") -> Workshop:
        return Workshop.objects.create(name=name)

    @classmethod
    def setup_vehicle(cls, workshop: Workshop, license_plate: str = "AB-123") -> Vehicle:
        return Vehicle.objects.create(workshop=workshop, license_plate=license_plate)
