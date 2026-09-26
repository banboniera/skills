from unittest.mock import patch

from tickets.models import Ticket
from tickets.tests.base import TicketsTestCase


class TicketViewSetTests(TicketsTestCase):
    def setUp(self):
        super().setUp()
        self.company = self.setup_company()
        self.other = self.setup_company("Other")
        self.admin = self.setup_member(self.company, "admin")
        self.agent = self.setup_member(self.company, "agent")

    def test_list_requires_login(self):
        response = self.client.get("/tickets/")
        self.assertIn(response.status_code, (401, 403))

    def test_list_returns_tickets(self):
        self.setup_ticket(self.company)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/tickets/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["results"])

    def test_list_hides_other_company_tickets(self):
        foreign = self.setup_ticket(self.other)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/tickets/")
        self.assertNotIn(foreign.pk, [row["id"] for row in response.data["results"]])

    def test_status_filter(self):
        self.setup_ticket(self.company, "one")
        self.setup_ticket(self.company, "two")
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/tickets/", {"status": "open"})
        self.assertEqual(len(response.data["results"]), 2)

    def test_list_query_count(self):
        self.setup_ticket(self.company)
        self.client.force_authenticate(user=self.admin)
        with self.assertNumQueries(2):
            self.client.get("/tickets/")

    def test_create_ticket(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/tickets/", {"title": "New"})
        self.assertEqual(response.status_code, 201)

    def test_admin_can_delete_ticket(self):
        ticket = self.setup_ticket(self.company)
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f"/tickets/{ticket.pk}/")
        self.assertEqual(response.status_code, 204)

    @patch("tickets.views.notify_ticket_closed")
    def test_close_ticket(self, notify):
        ticket = self.setup_ticket(self.company)
        self.client.force_authenticate(user=self.agent)
        response = self.client.post(f"/tickets/{ticket.pk}/close/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "closed")

    def test_agent_can_assign(self):
        ticket = self.setup_ticket(self.company)
        self.client.force_authenticate(user=self.agent)
        response = self.client.post(f"/tickets/{ticket.pk}/assign/", {"assignee": self.agent.pk})
        self.assertEqual(response.status_code, 200)

    def test_stats(self):
        self.setup_ticket(self.company)
        self.setup_ticket(self.company, status=Ticket.Status.CLOSED)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/tickets/stats/")
        self.assertEqual(response.data, {"open": 1, "closed": 1})
