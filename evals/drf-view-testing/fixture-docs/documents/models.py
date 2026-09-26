from django.conf import settings
from django.db import models


class Workspace(models.Model):
    name = models.CharField(max_length=100)


class Member(models.Model):
    class Role(models.TextChoices):
        READER = "reader"
        EDITOR = "editor"
        ADMIN = "admin"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="member")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="members")
    role = models.CharField(max_length=10, choices=Role.choices)


class Document(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "private"
        WORKSPACE = "workspace"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="documents")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.WORKSPACE)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
