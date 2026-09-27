from datetime import timedelta
from functools import partial

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from . import reminders


class Patient(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    is_active = models.BooleanField(default=True)
    anonymized = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="unique_patient_email_ci")]

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Patients are never removed: deleting anonymizes the record so appointment history stays intact."""
        self.name = "Removed patient"
        self.email = f"removed-{self.pk}@invalid.example"
        self.anonymized = True
        self.is_active = False
        self.save()
        return 0, {}

    @classmethod
    def purge_inactive(cls) -> int:
        """Remove every inactive patient's personal data, keeping their appointment history."""
        count, _ = cls.objects.filter(is_active=False, anonymized=False).delete()
        return count


class AppointmentQuerySet(models.QuerySet):
    def upcoming(self):
        """Appointments that have not started yet, excluding cancelled ones."""
        return self.filter(starts_at__gt=timezone.now())

    def for_patient(self, patient):
        return self.filter(patient=patient)


class Appointment(models.Model):
    MIN_MINUTES = 15
    MAX_MINUTES = 120

    patient = models.ForeignKey(Patient, models.CASCADE, related_name="appointments")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    cancelled = models.BooleanField(default=False)

    objects = AppointmentQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="appointment_ends_after_start"),
        ]

    def clean(self):
        """An appointment lasts between MIN_MINUTES and MAX_MINUTES, both inclusive."""
        if self.starts_at and self.ends_at:
            minutes = (self.ends_at - self.starts_at) / timedelta(minutes=1)
            if not self.MIN_MINUTES <= minutes < self.MAX_MINUTES:
                raise ValidationError({"ends_at": f"Appointments last {self.MIN_MINUTES} to {self.MAX_MINUTES} minutes."})

    def save(self, *args, **kwargs):
        """New bookings get a confirmation email once the booking is committed; later edits send nothing."""
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            transaction.on_commit(partial(reminders.send_booking_confirmation, self.pk))
