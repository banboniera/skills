"""Workshop app models — eval fixture for django-model-testing skill."""

import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from .tasks import notify_order_ready


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def for_workshop(self, workshop):
        return self.get_queryset().filter(workshop=workshop)


class Workshop(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class RepairOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"
        IN_PROGRESS = "in_progress"
        READY = "ready"
        CLOSED = "closed"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    workshop = models.ForeignKey(Workshop, on_delete=models.PROTECT, related_name="orders")
    number = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workshop", "number"], name="unique_order_number_per_workshop"),
            models.CheckConstraint(
                condition=models.Q(closed_at__isnull=True) | models.Q(closed_at__gte=models.F("opened_at")),
                name="closed_after_opened",
            ),
        ]

    def clean(self):
        if self.status == self.Status.CLOSED and self.closed_at is None:
            raise ValidationError({"closed_at": "Closed orders require a close timestamp."})
        if self.closed_at and self.closed_at < self.opened_at:
            raise ValidationError({"closed_at": "Cannot close before opening."})

    def save(self, *args, **kwargs):
        self.number = self.number.strip().upper()
        became_ready = self.status == self.Status.READY and (
            self._state.adding or not RepairOrder.all_objects.filter(pk=self.pk, status=self.Status.READY).exists()
        )
        super().save(*args, **kwargs)
        if became_ready:
            transaction.on_commit(lambda: notify_order_ready.delay(self.pk))

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])
