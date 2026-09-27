from unittest.mock import patch

from rest_framework import status

from tickets.models import Ticket
from tickets.tests.base import TicketsTestCase


class TicketViewSetTests(TicketsTestCase):
    def setUp(self):
        super().setUp()
        self.company = self.setup_company()
        self.other = self.setup_company("Other")
        self.viewer = self.setup_member(self.company, "viewer")
        self.agent = self.setup_member(self.company, "agent")
        self.admin = self.setup_member(self.company, "admin")
        self.outsider = self.setup_member(self.other, "admin")

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def ids(self, response):
        return [row["id"] for row in response.data["results"]]

    def test_anonymous_gets_401(self):
        for method, url in [("get", "/tickets/"), ("post", "/tickets/"), ("get", "/tickets/stats/")]:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_shows_company_live_tickets_newest_first(self):
        older = self.setup_ticket(self.company, "older")
        newer = self.setup_ticket(self.company, "newer")
        self.setup_ticket(self.company, archived=True)
        self.setup_ticket(self.other)
        self.as_user(self.viewer)
        self.assertEqual(self.ids(self.client.get("/tickets/")), [newer.pk, older.pk])

    def test_archived_list_shows_only_company_archived(self):
        archived = self.setup_ticket(self.company, archived=True)
        self.setup_ticket(self.company)
        self.setup_ticket(self.other, archived=True)
        self.as_user(self.viewer)
        self.assertEqual(self.ids(self.client.get("/tickets/", {"archived": "true"})), [archived.pk])

    def test_status_filter(self):
        closed = self.setup_ticket(self.company, status="closed")
        self.setup_ticket(self.company)
        self.as_user(self.viewer)
        self.assertEqual(self.ids(self.client.get("/tickets/", {"status": "closed"})), [closed.pk])

    def test_list_query_count_does_not_grow_with_rows(self):
        for _ in range(3):
            self.setup_ticket(self.company, assignee=self.agent)
        self.as_user(self.viewer)
        with self.assertNumQueries(2):  # count, rows (membership is cached on the user)
            self.client.get("/tickets/")

    def test_other_company_ticket_is_404(self):
        foreign = self.setup_ticket(self.other)
        self.as_user(self.admin)
        self.assertEqual(self.client.get(f"/tickets/{foreign.pk}/").status_code, 404)

    def test_viewer_cannot_write(self):
        ticket = self.setup_ticket(self.company)
        self.as_user(self.viewer)
        self.assertEqual(self.client.post("/tickets/", {"title": "x"}).status_code, 403)
        self.assertEqual(self.client.patch(f"/tickets/{ticket.pk}/", {"title": "x"}).status_code, 403)
        self.assertEqual(self.client.post(f"/tickets/{ticket.pk}/close/").status_code, 403)

    def test_create_sets_company_and_creator(self):
        self.as_user(self.agent)
        response = self.client.post("/tickets/", {"title": "New"})
        self.assertEqual(response.status_code, 201)
        ticket = Ticket.objects.get(pk=response.data["id"])
        self.assertEqual((ticket.company, ticket.created_by), (self.company, self.agent))

    def test_only_admin_deletes_and_delete_archives(self):
        ticket = self.setup_ticket(self.company)
        self.as_user(self.agent)
        self.assertEqual(self.client.delete(f"/tickets/{ticket.pk}/").status_code, 403)
        self.as_user(self.admin)
        self.assertEqual(self.client.delete(f"/tickets/{ticket.pk}/").status_code, 204)
        ticket.refresh_from_db()
        self.assertTrue(ticket.archived)

    @patch("tickets.views.notify_ticket_closed")
    def test_close_stamps_and_notifies_after_commit(self, notify):
        ticket = self.setup_ticket(self.company)
        self.as_user(self.agent)
        with self.captureOnCommitCallbacks() as callbacks:
            response = self.client.post(f"/tickets/{ticket.pk}/close/")
            notify.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        notify.assert_called_once_with(ticket.pk)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "closed")
        self.assertIsNotNone(ticket.closed_at)

    def test_closing_closed_ticket_is_400(self):
        ticket = self.setup_ticket(self.company, status="closed")
        self.as_user(self.agent)
        self.assertEqual(self.client.post(f"/tickets/{ticket.pk}/close/").status_code, 400)

    def test_close_other_company_ticket_is_404(self):
        foreign = self.setup_ticket(self.other)
        self.as_user(self.agent)
        self.assertEqual(self.client.post(f"/tickets/{foreign.pk}/close/").status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, "open")

    def test_assign_is_admin_only_and_company_members_only(self):
        ticket = self.setup_ticket(self.company)
        self.as_user(self.agent)
        self.assertEqual(self.client.post(f"/tickets/{ticket.pk}/assign/", {"assignee": self.agent.pk}).status_code, 403)
        self.as_user(self.admin)
        response = self.client.post(f"/tickets/{ticket.pk}/assign/", {"assignee": self.outsider.pk})
        self.assertEqual(response.status_code, 400)
        self.assertIn("assignee", response.data)
        self.assertEqual(self.client.post(f"/tickets/{ticket.pk}/assign/", {"assignee": self.agent.pk}).status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignee, self.agent)

    def test_stats_count_company_live_tickets(self):
        self.setup_ticket(self.company)
        self.setup_ticket(self.company, status="closed")
        self.setup_ticket(self.company, archived=True)
        self.setup_ticket(self.other)
        self.as_user(self.viewer)
        self.assertEqual(self.client.get("/tickets/stats/").data, {"open": 1, "closed": 1})
