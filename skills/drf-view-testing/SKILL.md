---
name: drf-view-testing
description: Writes, maintains, and reviews tests for Django REST Framework views and viewsets across their lifecycle so the tests catch real regressions — covering existing endpoints, changing an endpoint's access, queryset, actions, or responses test-first, deciding what to do when a view test starts failing (including after a DRF or django-filter upgrade), and reviewing existing view tests. Covers 401 vs 403, per-action permissions, tenant scoping on every route (broken object-level authorization), custom and inherited actions, writes and side effects, pagination, filters and ordering, disabled methods, and query counts. Use whenever a task writes, reviews, updates, or fixes tests for DRF views, viewsets, or API endpoints, and whenever it adds an endpoint or changes one's permissions, queryset, actions, or responses, since the tests change with it. Also use for an "add tests" request on code that turns out to be a DRF view, or a failing view test. Not for serializer or model tests.
---

# Testing DRF views

A view decides who may do what to which rows: it authenticates the caller, checks permissions per action, limits every route to the rows the caller may reach, and turns requests into writes and side effects. A view test exists to fail when any of that breaks. Coverage does not show that: a test can hit every route and still pass when the logic is wrong, because it asserts only a status code, or only for the role that is allowed. Every task below uses the standard in this file; read the reference that matches the task too.

| Task | Read |
| --- | --- |
| Add tests for endpoints that already exist | this file |
| Add or change an endpoint's access, queryset, actions, or responses, or a view test starts failing | this file and [references/changing-views.md](references/changing-views.md) |
| Review existing view tests | this file and [references/reviewing.md](references/reviewing.md) |

## The standard

A good view test states one rule the endpoint promises, sets up the smallest case where that rule makes a visible difference, and asserts the outcome exactly. Before keeping a test, ask: if someone deleted or inverted the code behind this rule, would this test fail? If not, it is decoration.

That question drives the choices below.

- **Expected values come from the promise, not the code.** The promise is what the view's docstring, the project's rules, and the API's clients say the endpoint does. Reading `get_permissions()` and asserting what it returns only proves the code equals itself, and it passes on the bug. When the promise and the code disagree, you have found a bug (see "When a test exposes a bug").
- **Test every caller that matters, not just the allowed one.** For each action: each role that may use it, each role that may not, an anonymous caller, and a caller from another tenant. A test run only as the most privileged role passes when a permission check is missing.
- **Seed the rows that must be left out.** Another tenant's rows, archived or deleted rows, rows a filter excludes. A list test whose every seeded row belongs in the result passes when the scoping or the filter is gone.
- **Assert the exact outcome.** The exact status code, the body keys the client reads (error keys, ids in the order promised), and, after a write, the stored rows reloaded from the database, including rows that must not have changed.
- **Assert what must not happen.** A refused request writes nothing and queues nothing; a request for another tenant's row changes nothing; a client-sent owner or tenant is ignored.

## Find the promise

Read the view and everything that gives it behavior before writing anything: the view class and every base and mixin it inherits (often in other modules, adding actions of their own), `get_queryset()`, `get_object()`, `permission_classes` and `get_permissions()`, `@action` decorators and their `permission_classes`, `get_serializer_class()`, `perform_create()`, `perform_update()`, `perform_destroy()`, `filter_backends` with their filter, search, and ordering fields, the pagination class, throttles, `http_method_names`, and the authentication classes in settings. Then read how the routes are registered, and what the clients rely on.

Follow the project's testing conventions: its base test classes, request and authentication helpers, fixtures, file layout, and test command. Look in AGENTS.md or CLAUDE.md, neighboring view tests, and CI config, and reuse what exists rather than hand-rolling setup.

Test what the view adds, not DRF or the serializer: leave field validation and output shape to serializer tests, and check here only that the view wires them in (a validation error reaches the client, `save()` receives the view's values).

## Behaviors and their traps

**Authentication.** Whether an anonymous caller gets 401 or 403 depends only on the first authentication class in effect: `TokenAuthentication` (and Knox) answer 401 with a `WWW-Authenticate` header, `SessionAuthentication` first or alone answers 403. Assert the exact code for the classes the project configures; `assertIn(status, (401, 403))` passes on the wrong one.

**Permissions.** DRF checks in this order: the URL must match (else 404), the method must be routed (else 405), then authentication and each permission's `has_permission()`, all of which must pass unless combined with `|` (401 or 403), then throttles (429), then the handler; `get_object()` first filters `get_queryset()` (404 when the row is outside it) and only then runs `has_object_permission()` (403). Build a matrix of roles against actions from the promise and test each cell, with `subTest` to keep it readable. `@action(permission_classes=[...])` replaces the view's permission classes rather than adding to them, and a branch in `get_permissions()` sends every action it does not name to its default branch: test each custom action on its own, especially new ones. Object permissions run only inside `get_object()`, so list routes and actions that load rows themselves skip them; test an object permission through each write action separately (update, partial update, destroy, each detail action).

**Tenant scoping on every route.** `get_queryset()` is the boundary, and broken object-level authorization is the most common API security bug. For every detail route (retrieve, update, partial update, destroy, and each `@action(detail=True)`), request a row outside the caller's scope, such as another tenant's, and expect 404 with the row unchanged; a list that hides a row proves nothing about the detail routes. Look for what bypasses the boundary: an action that loads rows itself (`Model.objects.get(pk=pk)`, `get_object_or_404(Model, ...)`), a branch of `get_queryset()` that rebuilds the queryset for a query parameter, and aggregate or export endpoints running their own queries.

**Writes.** Assert the status, the response fields the client uses, and the stored rows after reloading. Values the view passes to `serializer.save()` override the payload, and anything the serializer leaves writable is the client's to set: send an owner, tenant, or status in the payload and assert it was ignored, on create and on update. Soft deletes answer 204 and leave the row, marked. A refused or invalid request must leave the database unchanged: a view that writes before it raises keeps that write unless `ATOMIC_REQUESTS` is on, and even then only a request through the test client rolls back; a direct `view(request)` call never does.

**Side effects.** For a task or email queued with `transaction.on_commit()`, patch it where the view looks it up, wrap the request in `self.captureOnCommitCallbacks(execute=True)`, assert nothing ran inside the block, and assert the call with its arguments after it. `TestCase` never commits, so without capturing, the callback never runs and a test of it passes on anything. Assert that failure paths queue nothing.

**Lists.** Assert the ids in the promised order, with rows created in an order that differs from it; a paginated queryset needs an ordering ending in a unique field, or pages repeat and skip rows. For each filter, search, and ordering parameter, seed rows on both sides so the parameter changes the result, and keep another tenant's matching row in the data. Know what invalid input does: django-filter answers 400 keyed by the parameter for a bad number or choice, but silently ignores a bad boolean; `OrderingFilter` ignores fields not in `ordering_fields`; `PageNumberPagination` answers 404 for a page past the end. Assert the envelope the client reads, such as `count` and `results`.

**Routes and methods.** A method the view does not route on an existing URL answers 405, including a GET to a POST-only action; a URL the router never registered (a viewset without retrieve, update, or destroy has no detail route at all) answers 404. Test the ones the promise disables.

**Query count.** An endpoint's query count must not grow with its rows: seed at least two rows (ideally more) with the related data the response touches, and assert the exact count around the request. A count measured on one row, or on rows without related data, passes with an N+1 in place. `force_authenticate` skips the authentication queries a real token lookup would add.

**Errors.** Assert the body keys the client reads: a validation error's field keys, `{"detail": ...}` for permission and not-found errors. An unhandled exception reaches the test as the exception itself, not as a 500 response, so a test expecting 500 is a sign the view should answer a 4xx instead.

**Throttling.** Test it only when a limit is part of the promise. Throttle counters live in the cache, which `TestCase` does not reset: clear it in `setUp`.

## Writing the tests

```python
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from billing.models import Invoice, Membership, Org

class InvoiceViewSetTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Org.objects.create(name="Acme")
        cls.clerk = cls.member(cls.org, "clerk")
        cls.accountant = cls.member(cls.org, "accountant")
        cls.outsider = cls.member(Org.objects.create(name="Other"), "accountant")

    @staticmethod
    def member(org, role):
        user = get_user_model().objects.create_user(username=f"{role}-{org.name}")
        Membership.objects.create(user=user, org=org, role=role)
        return user

    def test_roles_per_action(self):
        invoice = Invoice.objects.create(org=self.org, number="A-1")
        cases = [  # (user, method, url, expected status) straight from the documented rules
            (None, "get", "/invoices/", status.HTTP_401_UNAUTHORIZED),
            (self.clerk, "get", "/invoices/", status.HTTP_200_OK),
            (self.clerk, "post", f"/invoices/{invoice.pk}/send/", status.HTTP_403_FORBIDDEN),
            (self.clerk, "delete", f"/invoices/{invoice.pk}/", status.HTTP_403_FORBIDDEN),
            (self.accountant, "patch", f"/invoices/{invoice.pk}/", status.HTTP_405_METHOD_NOT_ALLOWED),
        ]
        for user, method, url, expected in cases:
            with self.subTest(user=user, method=method, url=url):
                self.client.force_authenticate(user=user)
                self.assertEqual(getattr(self.client, method)(url).status_code, expected)

    def test_other_orgs_invoice_does_not_exist_on_any_detail_route(self):
        foreign = Invoice.objects.create(org=Org.objects.create(name="Else"), number="X-1")
        self.client.force_authenticate(user=self.accountant)
        for method, url in [("get", f"/invoices/{foreign.pk}/"), ("delete", f"/invoices/{foreign.pk}/"), ("post", f"/invoices/{foreign.pk}/send/")]:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url).status_code, status.HTTP_404_NOT_FOUND)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, "draft")

    def test_create_stores_the_callers_org_whatever_the_payload_says(self):
        self.client.force_authenticate(user=self.clerk)
        other_org = self.outsider.membership.org
        response = self.client.post("/invoices/", {"number": "A-2", "org": other_org.pk, "status": "sent"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        invoice = Invoice.objects.get(pk=response.data["id"])
        self.assertEqual((invoice.org, invoice.status), (self.org, "draft"))

    def test_status_filter_keeps_only_matching_invoices_of_the_org(self):
        sent = Invoice.objects.create(org=self.org, number="A-3", status="sent")
        Invoice.objects.create(org=self.org, number="A-4")
        Invoice.objects.create(org=self.outsider.membership.org, number="X-2", status="sent")
        self.client.force_authenticate(user=self.clerk)
        response = self.client.get("/invoices/", {"status": "sent"})
        self.assertEqual([row["id"] for row in response.data["results"]], [sent.pk])

    def test_list_runs_the_same_queries_for_any_number_of_rows(self):
        for n in range(3):
            Invoice.objects.create(org=self.org, number=f"B-{n}")
        self.client.force_authenticate(user=self.clerk)
        with self.assertNumQueries(2):  # count, then the page
            self.client.get("/invoices/")

    @patch("billing.emails.send_invoice_email")
    def test_send_marks_sent_and_emails_after_commit(self, send_email):
        invoice = Invoice.objects.create(org=self.org, number="A-5")
        self.client.force_authenticate(user=self.accountant)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/invoices/{invoice.pk}/send/")
            send_email.assert_not_called()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        send_email.assert_called_once_with(invoice.pk)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "sent")
```

- Go through the test client (`APITestCase`'s `self.client`, with `force_authenticate(user=..., token=...)` when the view reads `request.auth`): it exercises routing, method handling, and permissions the way production does. Calling `ViewSet.as_view({"get": "list"})(request)` on an `APIRequestFactory` request is faster and fine where the project does it, but it skips routing, so 404 and 405 behavior goes untested, it needs `force_authenticate()` on the request (setting `request.user` works only with session authentication), and detail actions need `pk=` passed to the call.
- `force_authenticate()` keeps the user object you pass; after changing that user in the database, pass the reloaded object. `force_authenticate(user=None)` switches back to anonymous.
- The test client sends multipart by default: pass `format="json"` for nested payloads, lists, and explicit nulls.
- Put rows most tests share in `setUpTestData`, and create the client-specific state in the test. Name each test after the rule it checks, so a failure reads as the broken promise.

## When a test exposes a bug

If a test written from the promise fails because the view breaks it, keep the test as written and failing, leave the view unchanged, and finish the rest. Never add a test that asserts behavior you believe is wrong, such as a role reaching an action it should not. In your report, name the failing test, the request, and what the promise says, so the user can decide whether to fix the view. This applies to bugs you find; a change the user asked for follows [references/changing-views.md](references/changing-views.md).

## Finish

Run the new or changed tests with the project's test command, limited to the modules you touched. They pass, except tests you kept because they expose a bug.

Report what you tested, the bugs found with their failing tests, and anything the tests cannot prove, such as behavior that depends on production settings the tests replace.

For many views at once with subagents, give each subagent a whole module, since sibling views share bases and fixtures, and have them write tests only; run the new test modules one at a time at the end, because parallel `manage.py test` runs can collide on a shared test database.
