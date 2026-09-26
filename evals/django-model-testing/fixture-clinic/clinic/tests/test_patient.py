from django.test import TestCase

from clinic.models import Patient


class PatientTests(TestCase):
    def test_new_patient_is_active(self):
        self.assertTrue(Patient.objects.create(name="Ann", email="ann@example.com").is_active)
