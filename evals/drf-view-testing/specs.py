"""Planted bugs and mutants for each eval fixture. Each fix turns the shipped (buggy) views into correct code."""

# Bug 1: the close action looks the ticket up directly instead of through get_object(), so any company's ticket closes.
BUGGY_CLOSE = "        ticket = Ticket.objects.get(pk=pk)\n        if ticket.status"
FIXED_CLOSE = "        ticket = self.get_object()\n        if ticket.status"
# Bug 2: assign is admin-only, but get_permissions lets agents through.
BUGGY_ASSIGN = 'elif self.action == "destroy":'
FIXED_ASSIGN = 'elif self.action in ("destroy", "assign"):'
# Bug 3: ?archived=true rebuilds the queryset without the company filter.
BUGGY_ARCHIVED = "tickets = Ticket.objects.filter(archived=True)"
FIXED_ARCHIVED = "tickets = Ticket.objects.filter(company=self.company, archived=True)"
HELPDESK_FIXES = [(BUGGY_CLOSE, FIXED_CLOSE), (BUGGY_ASSIGN, FIXED_ASSIGN), (BUGGY_ARCHIVED, FIXED_ARCHIVED)]
HELPDESK_MUTANTS = [
    ("list shows other companies' tickets", "tickets = Ticket.objects.filter(company=self.company, archived=False)", "tickets = Ticket.objects.filter(archived=False)"),
    ("list shows archived tickets", "tickets = Ticket.objects.filter(company=self.company, archived=False)", "tickets = Ticket.objects.filter(company=self.company)"),
    ("archived list shows other companies'", FIXED_ARCHIVED, BUGGY_ARCHIVED),
    ("archived list shows live tickets", FIXED_ARCHIVED, "tickets = Ticket.objects.filter(company=self.company)"),
    ("status filter ignored", "            tickets = tickets.filter(status=status_filter)\n", "            pass\n"),
    ("list oldest first", 'order_by("-created_at", "-pk")', 'order_by("created_at", "pk")'),
    ("list queries assignee per row", '.select_related("assignee")', ""),
    ("viewer can write", "            roles = (Membership.Role.AGENT, Membership.Role.ADMIN)\n", "            roles = (Membership.Role.VIEWER, Membership.Role.AGENT, Membership.Role.ADMIN)\n"),
    ("agent can delete", FIXED_ASSIGN, 'elif self.action == "assign":'),
    ("agent can assign", FIXED_ASSIGN, BUGGY_ASSIGN),
    ("anonymous gets a server error instead of 401", "return [IsAuthenticated(), HasRole(roles)]", "return [HasRole(roles)] if self.action != \"list\" else []"),
    ("created_by not set", "serializer.save(company=self.company, created_by=self.request.user)", "serializer.save(company=self.company)"),
    ("delete removes the row", '        ticket.archived = True\n        ticket.save(update_fields=["archived"])\n', "        ticket.delete()\n"),
    ("close reaches other companies' tickets", FIXED_CLOSE, BUGGY_CLOSE),
    ("closing a closed ticket allowed", "        if ticket.status == Ticket.Status.CLOSED:\n", "        if False:\n"),
    ("closed_at not stamped", "        ticket.closed_at = timezone.now()\n", ""),
    ("notification sent before commit", "transaction.on_commit(lambda: notify_ticket_closed(ticket.pk))", "notify_ticket_closed(ticket.pk)"),
    ("no notification", "        transaction.on_commit(lambda: notify_ticket_closed(ticket.pk))\n", ""),
    ("assign accepts other companies' users", "filter(pk=user_id, membership__company=self.company)", "filter(pk=user_id)"),
    ("stats count other companies", "            Ticket.objects.filter(company=self.company, archived=False)\n            .values_list", "            Ticket.objects.filter(archived=False)\n            .values_list"),
    ("stats count archived", "            Ticket.objects.filter(company=self.company, archived=False)\n            .values_list", "            Ticket.objects.filter(company=self.company)\n            .values_list"),
]

# Held-out fixture. Bug 1: visibility is filtered only in list(), so detail routes reach others' private documents.
BUGGY_VISIBLE = "            Document.objects.filter(workspace=self.workspace, deleted_at__isnull=True)\n            .select_related"
FIXED_VISIBLE = (
    "            Document.objects.filter(workspace=self.workspace, deleted_at__isnull=True)\n"
    "            .filter(Q(visibility=Document.Visibility.WORKSPACE) | Q(owner=self.request.user))\n"
    "            .select_related"
)
# Bug 2: the object permission covers PUT and PATCH but not DELETE.
BUGGY_DELETE = 'if request.method in ("PUT", "PATCH"):'
FIXED_DELETE = "if request.method not in SAFE_METHODS:"
# Bug 3: the owner is writable, so a client can create or move documents under someone else's name.
BUGGY_OWNER_FIELD = 'read_only_fields = ["created_at"]'
FIXED_OWNER_FIELD = 'read_only_fields = ["owner", "created_at"]'
BUGGY_OWNER_SAVE = "serializer.save(workspace=self.workspace)"
FIXED_OWNER_SAVE = "serializer.save(workspace=self.workspace, owner=self.request.user)"
DOCS_FIXES = [(BUGGY_VISIBLE, FIXED_VISIBLE), (BUGGY_DELETE, FIXED_DELETE), (BUGGY_OWNER_FIELD, FIXED_OWNER_FIELD), (BUGGY_OWNER_SAVE, FIXED_OWNER_SAVE)]
DOCS_MUTANTS = [
    ("other workspaces' documents visible", "Document.objects.filter(workspace=self.workspace, deleted_at__isnull=True)", "Document.objects.filter(deleted_at__isnull=True)"),
    ("deleted documents visible", "Document.objects.filter(workspace=self.workspace, deleted_at__isnull=True)", "Document.objects.filter(workspace=self.workspace)"),
    ("others' private documents reachable by id", FIXED_VISIBLE, BUGGY_VISIBLE),
    ("own private documents hidden", "Q(visibility=Document.Visibility.WORKSPACE) | Q(owner=self.request.user))\n", "Q(visibility=Document.Visibility.WORKSPACE))\n"),
    ("search ignored", 'search_fields = ["title"]', "search_fields = []"),
    ("ordering by title ignored", 'ordering_fields = ["title", "created_at"]', 'ordering_fields = ["created_at"]'),
    ("oldest first by default", 'order_by("-created_at", "-pk")', 'order_by("created_at", "pk")'),
    ("owner queried per row", '.select_related("owner")', ""),
    ("reader can write", "return request.method in SAFE_METHODS or member.role in (Member.Role.EDITOR, Member.Role.ADMIN)", "return True"),
    ("editor can restore", "return member.role == Member.Role.ADMIN", "return member.role != Member.Role.READER"),
    ("editor can delete others' documents", FIXED_DELETE, BUGGY_DELETE),
    ("editor can edit others' documents", "return document.owner_id == request.user.pk or request.user.member.role == Member.Role.ADMIN", "return True"),
    ("owner cannot edit own document", "return document.owner_id == request.user.pk or request.user.member.role == Member.Role.ADMIN", "return request.user.member.role == Member.Role.ADMIN"),
    ("delete removes the row", '        document.deleted_at = timezone.now()\n        document.save(update_fields=["deleted_at"])\n', "        document.delete()\n"),
    ("owner writable on update", FIXED_OWNER_FIELD, BUGGY_OWNER_FIELD),
    ("restore reaches other workspaces", "pk=pk, workspace=self.workspace, deleted_at__isnull=False", "pk=pk, deleted_at__isnull=False"),
    ("restore leaves the document deleted", "        document.deleted_at = None\n", ""),
]

# Change task: viewers may create tickets (and nothing else they could not do before), on the corrected helpdesk views.
VIEWER_FIXES = [
    ('if self.action in ("list", "retrieve", "stats"):', 'if self.action in ("list", "retrieve", "stats", "create"):'),
    ("Everyone in the company reads. Agents and admins create, edit, and close.", "Everyone in the company reads and creates. Agents and admins edit and close."),
]
CHANGE_MUTANTS = [
    ("viewers cannot create", 'if self.action in ("list", "retrieve", "stats", "create"):', 'if self.action in ("list", "retrieve", "stats"):'),
    ("viewers can edit and close", "            roles = (Membership.Role.AGENT, Membership.Role.ADMIN)\n", "            roles = (Membership.Role.VIEWER, Membership.Role.AGENT, Membership.Role.ADMIN)\n"),
] + [m for m in HELPDESK_MUTANTS if m[0] in ("list shows other companies' tickets", "created_by not set", "agent can delete", "agent can assign", "close reaches other companies' tickets", "delete removes the row")]
VIEWER_FINAL_TEST = """from tickets.models import Ticket
from tickets.tests.base import TicketsTestCase


class ViewerCreatesTests(TicketsTestCase):
    def setUp(self):
        super().setUp()
        self.company = self.setup_company()
        self.viewer = self.setup_member(self.company, "viewer")
        self.client.force_authenticate(user=self.viewer)

    def test_viewer_creates_ticket(self):
        response = self.client.post("/tickets/", {"title": "New"})
        self.assertEqual(response.status_code, 201)
        ticket = Ticket.objects.get(pk=response.data["id"])
        self.assertEqual((ticket.company, ticket.created_by), (self.company, self.viewer))

    def test_viewer_still_cannot_change_tickets(self):
        ticket = self.setup_ticket(self.company)
        for method, url in [("patch", f"/tickets/{ticket.pk}/"), ("put", f"/tickets/{ticket.pk}/"), ("post", f"/tickets/{ticket.pk}/close/"), ("delete", f"/tickets/{ticket.pk}/")]:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, {"title": "x"}).status_code, 403)
"""

SPECS = {
    "helpdesk": {
        "fixture": "helpdesk",
        "app": "tickets",
        "target": "tickets/views.py",
        "fixes": HELPDESK_FIXES,
        "mutants": HELPDESK_MUTANTS,
        "untouched": ["tickets/views.py", "tickets/permissions.py", "tickets/serializers.py", "tickets/models.py"],
        "base_class": "TicketsTestCase",
        "reports": [
            ("Report names the cross-company close bug", [r"(?i)close", r"(?i)other company|another company|other compan|cross-company|get_object|tenant|scop"]),
            ("Report names the agent-assign bug", [r"(?i)assign", r"(?i)agent"]),
            ("Report names the unscoped archived list", [r"(?i)archived", r"(?i)other company|another company|other compan|cross-company|tenant|scop|leak"]),
        ],
    },
    "docs": {
        "fixture": "docs",
        "app": "documents",
        "target": "documents/views.py",
        "fixes": DOCS_FIXES,
        "mutants": DOCS_MUTANTS,
        "untouched": ["documents/views.py", "documents/models.py"],
        "base_class": "DocumentsTestCase",
        "test_patterns": [("Tests cover the inherited export action", r"export")],
        "reports": [
            ("Report names the private-document detail leak", [r"(?i)private", r"(?i)retriev|detail|by id|get_queryset|/documents/\{?\w*\}?/|404"]),
            ("Report names the delete permission bug", [r"(?i)delet", r"(?i)DELETE|owner|admin|editor|permission"]),
            ("Report names the writable owner", [r"(?i)owner", r"(?i)writable|read.only|mass assign|payload|someone else|another user|other user|spoof|any user"]),
        ],
    },
    "change": {
        "fixture": "change",
        "app": "tickets",
        "target": "tickets/views.py",
        "fixes": VIEWER_FIXES,
        "mutants": CHANGE_MUTANTS,
        "change": True,
        "min_tests": 14,
        "final_tests": {"test_zzz_viewer_creates.py": VIEWER_FINAL_TEST},
        "stale_label": "No test still expects viewers to be refused",
        "reports": [("Lists the test whose expectation changed", [r"(?i)test_viewer_cannot_write|viewer[^.\n]{0,120}(updat|chang|adjust|split|rewr)"])],
    },
}
