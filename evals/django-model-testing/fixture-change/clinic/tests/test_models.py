from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from clinic.models import Appointment, Patient


class ClinicModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ann = Patient.objects.create(name="Ann", email="ann@example.com")

    def _appt(self, minutes, start=None, **kw):
        start = start or timezone.now() + timedelta(days=1)
        return Appointment(patient=self.ann, starts_at=start, ends_at=start + timedelta(minutes=minutes), **kw)

    def test_email(self):
        p = Patient.objects.create(name="B", email="  Bob@Example.com ")
        p.refresh_from_db()
        self.assertEqual(p.email, "bob@example.com")
        with self.assertRaises(ValidationError):
            Patient(name="X", email="ANN@example.com").full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Patient.objects.create(name="Y", email="ann@example.com")

    def test_delete(self):
        p = Patient.objects.create(name="Cy", email="cy@example.com")
        p.delete()
        p.refresh_from_db()
        self.assertEqual((p.name, p.is_active, p.anonymized), ("Removed patient", False, True))

    def test_purge(self):
        gone = Patient.objects.create(name="Old", email="old@example.com", is_active=False)
        Appointment.objects.create(patient=gone, starts_at=timezone.now(), ends_at=timezone.now() + timedelta(minutes=30))
        self.assertEqual(Patient.purge_inactive(), 1)
        gone.refresh_from_db()
        self.assertTrue(gone.anonymized)
        self.assertEqual(gone.appointments.count(), 1)
        self.ann.refresh_from_db()
        self.assertFalse(self.ann.anonymized)

    def test_querysets(self):
        other = Patient.objects.create(name="O", email="o@example.com")
        future = self._appt(30); future.save()
        self._appt(30, cancelled=True).save()
        self._appt(30, start=timezone.now() - timedelta(days=1)).save()
        Appointment(patient=other, starts_at=future.starts_at, ends_at=future.ends_at).save()
        self.assertEqual(set(Appointment.objects.for_patient(self.ann).upcoming()), {future})

    def test_length(self):
        self._appt(15).full_clean()
        self._appt(120).full_clean()
        for m in (14, 121):
            with self.subTest(m=m), self.assertRaises(ValidationError) as ctx:
                self._appt(m).full_clean()
            self.assertIn("ends_at", ctx.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._appt(0).save()

    @patch("clinic.models.reminders.send_booking_confirmation")
    def test_confirmation(self, send):
        with self.captureOnCommitCallbacks() as callbacks:
            a = self._appt(30); a.save()
        send.assert_not_called()
        for cb in callbacks: cb()
        send.assert_called_once_with(a.pk)
        with self.captureOnCommitCallbacks(execute=True):
            a.cancelled = True; a.save()
        send.assert_called_once()
