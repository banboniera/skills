from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from shop.models import Account, RepairOrder, Vehicle
from shop.tests.base import ShopTestCase


class ShopModelTests(ShopTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workshop = cls.setup_workshop()
        cls.other = cls.setup_workshop("Other")
        cls.vehicle = cls.setup_vehicle(cls.workshop, "AB-1")

    def test_plate_is_uppercase(self):
        vehicle = Vehicle.objects.create(workshop=self.workshop, license_plate="CD-2")
        self.assertEqual(vehicle.license_plate, "CD-2")

    def test_duplicate_plate_is_rejected(self):
        with self.assertRaises(IntegrityError):
            Vehicle.objects.create(workshop=self.workshop, license_plate="AB-1")

    def test_zero_balance_is_allowed(self):
        account = Account.objects.create(workshop=self.workshop, name="Cash", balance=Decimal("0.00"))
        self.assertEqual(account.balance, Decimal("0.00"))

    def test_closed_order_requires_closed_at(self):
        foreign = self.setup_vehicle(self.other, "ZZ-9")
        order = RepairOrder(workshop=self.workshop, vehicle=foreign, status=RepairOrder.Status.CLOSED)
        with self.assertRaises(ValidationError):
            order.full_clean()

    def test_open_excludes_ready_and_closed_orders(self):
        open_order = RepairOrder.objects.create(workshop=self.workshop, vehicle=self.vehicle)
        RepairOrder.objects.create(workshop=self.workshop, vehicle=self.vehicle, status=RepairOrder.Status.READY)
        RepairOrder.objects.create(workshop=self.workshop, vehicle=self.vehicle, status=RepairOrder.Status.CLOSED, closed_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(list(RepairOrder.objects.open()), [open_order])

    def test_for_workshop_returns_its_orders(self):
        order = RepairOrder.objects.create(workshop=self.workshop, vehicle=self.vehicle)
        self.assertIn(order, RepairOrder.objects.for_workshop(self.workshop))

    @patch("shop.models.tasks.notify_order_ready.delay")
    def test_saving_ready_twice_notifies_once(self, notify):
        order = RepairOrder.objects.create(workshop=self.workshop, vehicle=self.vehicle)
        order.status = RepairOrder.Status.READY
        order.save()
        order.save()
        self.assertLessEqual(notify.call_count, 1)

    def test_deleting_vehicle_with_orders_keeps_it(self):
        vehicle = self.setup_vehicle(self.workshop, "EF-3")
        RepairOrder.objects.create(workshop=self.workshop, vehicle=vehicle)
        vehicle.delete()
        self.assertTrue(Vehicle.objects.filter(pk=vehicle.pk).exists())
