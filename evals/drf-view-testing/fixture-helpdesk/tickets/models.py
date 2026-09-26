from django.conf import settings
from django.db import models


class Company(models.Model):
    name = models.CharField(max_length=100)


class Membership(models.Model):
    class Role(models.TextChoices):
        VIEWER = "viewer"
        AGENT = "agent"
        ADMIN = "admin"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices)


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="tickets")
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    archived = models.BooleanField(default=False)
