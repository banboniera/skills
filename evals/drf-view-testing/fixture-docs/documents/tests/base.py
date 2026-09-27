from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, APITestCase

from documents.models import Document, Member, Workspace


class DocumentsTestCase(APITestCase):
    """Base for view tests: fixture builders. `self.client` is an APIClient; `self.factory` an APIRequestFactory."""

    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()

    def setup_workspace(self, name="Team"):
        return Workspace.objects.create(name=name)

    def setup_member(self, workspace, role, username=None):
        """A user who is a member of `workspace` with `role` (reader, editor, or admin)."""
        user = get_user_model().objects.create_user(username=username or f"{role}-{workspace.pk}")
        Member.objects.create(user=user, workspace=workspace, role=role)
        return user

    def setup_document(self, workspace, owner, title="Notes", **fields):
        return Document.objects.create(workspace=workspace, owner=owner, title=title, **fields)
