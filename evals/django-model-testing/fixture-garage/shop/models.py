from decimal import Decimal
from functools import partial

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from . import tasks


class Workshop(models.Model):
    name = models.CharField(max_length=100)

    def open_order_count(self) -> int:
        """Orders still in the workshop: everything not closed yet, including orders ready for pickup."""
        return self.orders.open().count()


class Account(models.Model):
    workshop = models.ForeignKey(Workshop, models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=100)
    balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )


class VehicleQuerySet(models.QuerySet):
    def alive(self):
        """Vehicles that were not deleted."""
        return self.filter(is_deleted=False)

    def delete(self):
        """Delete through each instance, so bulk deletes follow the same keep-history rule."""
        count = 0
        for vehicle in self:
            deleted, _ = vehicle.delete()
            count += deleted
        return count, {self.model._meta.label: count}


class Vehicle(models.Model):
    workshop = models.ForeignKey(Workshop, models.CASCADE, related_name="vehicles")
    license_plate = models.CharField(max_length=16)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = VehicleQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workshop", "license_plate"],
                condition=Q(is_deleted=False),
                name="unique_live_plate_per_workshop",
            )
        ]

    def save(self, *args, **kwargs):
        """Store plates trimmed and uppercase, so lookups match however staff typed them."""
        self.license_plate = self.license_plate.strip().upper()
        if (update_fields := kwargs.get("update_fields")) is not None:
            kwargs["update_fields"] = {"license_plate", *update_fields}
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Vehicles with repair orders are kept for the record and only marked deleted; others are removed."""
        if self.orders.exists():
            self.is_deleted = True
            self.deleted_at = timezone.now()
            self.save(update_fields=["is_deleted", "deleted_at"])
            return 0, {}
        return super().delete(*args, **kwargs)


class RepairOrderQuerySet(models.QuerySet):
    def for_workshop(self, workshop):
        return self.filter(workshop=workshop)

    def open(self):
        """Orders not closed yet."""
        return self.filter(status=RepairOrder.Status.OPEN)


class RepairOrder(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        READY = "ready"
        CLOSED = "closed"

    workshop = models.ForeignKey(Workshop, models.CASCADE, related_name="orders")
    vehicle = models.ForeignKey(Vehicle, models.PROTECT, related_name="orders")
    status = models.CharField(max_length=10, choices=Status, default=Status.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = RepairOrderQuerySet.as_manager()

    def clean(self):
        errors = {}
        if self.status == self.Status.CLOSED and self.closed_at is None:
            errors["closed_at"] = "A closed order needs a closing time."
        if self.closed_at and self.closed_at > timezone.now():
            errors["closed_at"] = "The closing time cannot be in the future."
        if self.vehicle_id and self.workshop_id and self.vehicle.workshop_id != self.workshop_id:
            errors["vehicle"] = "The vehicle belongs to another workshop."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Tell the customer once, after the transaction commits, when the order becomes ready."""
        became_ready = False
        if self.status == self.Status.READY:
            previous = RepairOrder.objects.filter(pk=self.pk).values_list("status", flat=True).first()
            became_ready = previous != self.Status.READY
        super().save(*args, **kwargs)
        if became_ready:
            transaction.on_commit(partial(tasks.notify_order_ready.delay, self.pk))
