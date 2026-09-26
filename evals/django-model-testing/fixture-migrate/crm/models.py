from django.db import models


class Contact(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=30)
    phone_digits = models.CharField(max_length=20, blank=True)
    note = models.CharField(max_length=50, blank=True)
