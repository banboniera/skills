from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, APITestCase

from tickets.models import Company, Membership, Ticket


class TicketsTestCase(APITestCase):
    """Base for view tests: fixture builders. `self.client` is an APIClient; `self.factory` an APIRequestFactory."""

    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()

    def setup_company(self, name="Acme"):
        return Company.objects.create(name=name)

    def setup_member(self, company, role, username=None):
        """A user with a membership in `company` with `role` (viewer, agent, or admin)."""
        user = get_user_model().objects.create_user(username=username or f"{role}-{company.pk}")
        Membership.objects.create(user=user, company=company, role=role)
        return user

    def setup_ticket(self, company, title="Printer down", **fields):
        return Ticket.objects.create(company=company, title=title, **fields)
