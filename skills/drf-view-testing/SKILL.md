---
name: drf-view-testing
description: Write tests for Django REST Framework views and viewsets — endpoint contracts, auth, permissions, tenant scoping, pagination, filters, writes with DB side effects, custom @action endpoints. Use whenever user asks to test, cover, or verify a DRF view, ViewSet, API endpoint, or route, mentions APIClient, APIRequestFactory, force_authenticate, permission/403/401 tests, or asks for tests for views.py files or tests under tests/views/, even if they just say "add tests" for code that turns out to be a view.
---

# DRF View Testing

Test **endpoint contract**: status, response shape, access, scoping, DB side effects. Never re-test serializer/model internals — own suites cover those. View test answers: this URL, this caller, this payload — this observable outcome?

**User naming one behavior never shrinks contract.** "Test pagination" still means: auth statuses, invalid input, scoping for that endpoint. Quick-verify list = gate, not suggestion.

## Workflow

1. **Read view + all it touches**: ViewSet, every inherited mixin (shared bases add pagination validation, per-action serializers, extra `@action`s), `get_queryset()` scoping, permission classes, throttles, URLconf. No test for untraced contract. Asked to cover a view: **enumerate its actions** (router defaults + every `@action`) — cover each or name exclusions.
2. **Find project view test base** before raw boilerplate (here: `app.shared.tests.ViewTestCase` — see [Project conventions](#project-conventions)). Reuse fixtures + request builders.
3. **Pick invocation level** (ladder below).
4. **Write tests**: one behavior per test, behavior-named, exact assertions. Shared fixtures `setUpTestData`, per-test mutable state `setUp`. Path: `<app>/tests/views/test_<name>.py`.
5. **Run touched module only**, not whole suite.

## Invocation ladder

| Level | When | How |
|-------|------|-----|
| **Direct viewset call** (default) | Contract = action itself | `APIRequestFactory` + `force_authenticate(request, user=…, token=…)` + `ViewSet.as_view({"get": "list"})(request)` — no middleware/routing noise |
| **`APIClient` + `force_authenticate`** | Routing, headers, content negotiation, multipart, download part of contract | `client.force_authenticate(user=…, token=…)` then `client.get(url)` |
| **Full HTTP flow** | Auth mechanism itself under test | Real login (`POST /auth/login/`), then `client.credentials(HTTP_AUTHORIZATION="Token " + token)` |

`APIRequestFactory` returns Django `HttpRequest`, not DRF `Request` — setting `.user`/`.token` directly does nothing; always `force_authenticate`.

## What to cover

| Area | Do |
|------|-----|
| **Auth** | Allowed, **unauthenticated**, **forbidden** when access matters. Unauthenticated status must match **configured** auth classes (token auth = `401`). Real client flow only when **auth mechanism** itself under test. |
| **Permissions** | Endpoint-specific permission branches — **every allowed role** + rejected roles; **disabled actions**; exact **`403`** or **`405`**. DRF check order: URL `404` → method `405` → `has_permission` `403` → queryset `404` → object permission `403` — asserted status must match the stage that fires. |
| **Scoping** | Endpoints narrowed by request context (company/tenant/user): create out-of-scope row, assert never appears; correct failure contract (`404` vs `403`) for **out-of-scope** detail. Missing scoping test = security gap. |
| **List** | Actual list shape (e.g. `{"total", "results"}`). Pagination enabled/required: pagination fields + **invalid** pagination input (`400` + error keys). |
| **Date range** | Required range: missing, bad format, reversed bounds, valid range. |
| **Filter / search / order** | Only what endpoint exposes. Seed **discriminating** data: search term matching all rows, or expected order equal to insertion order, proves nothing. Included rows, excluded rows, **order** when order is contract. |
| **Shared view mixins** | Shared logic changing serializer by action or returning status-only responses — assert contract once per concrete view relying on it. |
| **Custom payload** | Extra top-level keys, aggregates, derived collections — assert explicitly. |
| **Validation** | Important error **keys/messages** in response — never stop at `400`. |
| **Writes** | Success + ≥1 invalid case. Response contract + **persisted** side effects (`refresh_from_db` / re-query); **unchanged** DB on reject. Detail writes (update/delete/custom detail actions): include **out-of-scope pk** case. |
| **Protected delete** | Delete can fail (related rows, guards): error contract + **DB unchanged**. |
| **Custom `@action`** | Each action = own contract: success, auth, scoping, validation, side effects as applicable. |
| **Shared extra actions** | by-pks, relation management, confirm, download, uploaded-only lists — contract + visible state changes. **No** storage-internals tests. |
| **Query budget** | Heavy list/action endpoints: `assertNumQueries(n)` with enough fixture rows that N+1 breaks count. |
| **Throttling** | Only when behavior depends on throttling or endpoint auth-heavy/public — not default. |

## Core patterns

**Direct action call — success for allowed caller:**

```python
def test_check_license_plate_returns_owner_for_manager(self):
    request = self._manager_request("get", self._check_license_plate_url(),
                                    {"license_plate": self.vehicle.license_plate})
    response = VehicleViewSet.as_view({"get": "check_license_plate"})(request)

    self.assertEqual(response.status_code, status.HTTP_200_OK)
    self.assertEqual(response.data["owner"]["id"], self.owner.pk)
```

**Access + input contract, one behavior-named test — exact statuses, never "fails":**

```python
def test_list_rejects_unauthenticated_non_manager_and_invalid_pagination(self):
    view = CustomerViewSet.as_view({"get": "list"})

    request = self.build_request("get", self.list_url, self._list_params())
    self.assertEqual(view(request).status_code, status.HTTP_401_UNAUTHORIZED)

    request = self.build_authenticated_request(
        "get", self.list_url, self._list_params(),
        user=self.employee_user, company=self.company, employee=self.employee,
    )
    self.assertEqual(view(request).status_code, status.HTTP_403_FORBIDDEN)

    request = self._manager_request("get", self.list_url, {})  # missing pagination
    response = view(request)
    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn("pageSize", response.data)
```

**Scoping — excluded row is the assertion that matters:**

```python
def test_list_returns_only_company_customers(self):
    response = self._list_response()

    pks = {row["id"] for row in response.data["results"]}
    self.assertIn(self.customer.pk, pks)
    self.assertNotIn(self.other_company_customer.pk, pks)
```

**Write — response contract, persisted state, reject leaves DB clean:**

```python
def test_create_persists_vehicle(self):
    request = self._manager_request("post", self.list_url, self._payload())
    response = self.create_view(request)

    self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    vehicle = Vehicle.objects.get(pk=response.data["id"])
    self.assertEqual(vehicle.company, self.company)

def test_create_rejects_missing_vin_and_persists_nothing(self):
    request = self._manager_request("post", self.list_url, self._payload(vin=""))
    response = self.create_view(request)

    self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    self.assertIn("vin", response.data)
    self.assertEqual(Vehicle.objects.count(), self.initial_vehicle_count)
```

**APIClient when routing/headers/downloads are contract — same token shape view reads:**

```python
self.client = APIClient()
self.client.force_authenticate(
    user=self.manager_user,
    token=SimpleNamespace(company=self.company, employee=self.manager),
)
response = self.client.get(self.list_url, data=self._completed_list_params())
```

**Query budget — seed enough rows that N+1 breaks count:**

```python
with self.assertNumQueries(12):
    response = CustomerViewSet.as_view({"get": "mutual_settlement"})(request)
```

**Repetition across actions = one helper, never copy-paste:**

```python
def test_check_license_plate_rejects_non_manager_and_anonymous_requests(self):
    self._assert_action_rejects_non_manager_and_anonymous(
        method="get",
        path=self._check_license_plate_url(),
        action="check_license_plate",
        data={"license_plate": self.vehicle.license_plate},
    )
```

## Anti-patterns

- Only status code on writes — contract includes what persisted (or didn't).
- Full response blob when few fields prove behavior — brittle, unreadable.
- Re-testing serializer field validation serializer suite covers; assert view surfaces error key, not every message variant.
- `403` asserted where configured auth classes return `401` for anonymous — know which before writing.
- Splitting one contract into many single-assert micro-tests — batch related rejections into one behavior-named test (see access pattern above); more tests ≠ more coverage.
- Multipart uploads: `APIRequestFactory`/`APIClient` need `format="multipart"`; dicts inside multipart data stringify to invalid JSON — flatten payload or post JSON separately.
- Setting `request.user` on `APIRequestFactory` request instead of `force_authenticate` — silently unauthenticated.
- Reusing one user instance across mutating tests without `refresh_from_db()` — `force_authenticate` binds in-memory object.
- Per-test fixtures every test needs — `setUpTestData` (once per class, transaction-isolated per test).
- Throttling, storage internals, middleware tests on every view "for completeness".

## Version notes (Python 3.14, Django 6.1, DRF 3.18, Knox 5)

- DRF 3.18: list serializer (`many=True`) validation errors now **dict format** — assert new shape on bulk endpoints, not old list-of-dicts.
- Knox token auth (project `CachedTokenAuthentication` subclasses it): anonymous = **`401`**, wrong-role authenticated = **`403`**. Project tests assert exactly this split.
- `setUpTestData` attributes deep-copied per test; Django 6.0+ requires deepcopyable — no clients/connections on class; create `APIClient` in `setUp`.
- Django 6 `DiscoverRunner` supports forkserver — `--parallel auto` cheap; keep tests isolation-safe.
- DRF 3.17+ enforces `DATA_UPLOAD_MAX_MEMORY_SIZE` for `request.data` parsing — matters only for upload-limit contracts.

## Project conventions

HuggingCar `api` project: read [references/huggingcar-api.md](references/huggingcar-api.md) before writing tests — test base (`app.shared.tests.ViewTestCase`, fixtures, request builders), shared view mixin inventory, Knox auth per role, test paths, run command. Other projects: find equivalent shared test base + conventions first.

## Quick verify (gate before finishing — applies even when user asked for one behavior)

Success path for allowed caller. Unauth/forbidden with **exact** status when access matters. Scoping: in-scope visible, out-of-scope excluded + correct detail failure. Pagination + date input where required; filter/search/order when exposed. Create/update/partial/delete/custom actions: DB side effects from persisted state + unchanged DB on reject. Shape includes custom top-level keys. Validation + permission errors by key/message. Disabled actions = expected `403`/`405`. Shared inherited contracts (by-pks, select-all, confirm/download) covered where exposed. Helpers OK; tests small, explicit, behavior-named.

## References

- https://www.django-rest-framework.org/api-guide/testing/
- https://www.django-rest-framework.org/api-guide/viewsets/
- https://www.django-rest-framework.org/community/release-notes/
- https://www.vintasoftware.com/blog/counting-queries-basic-performance-testing-in-django
- https://docs.djangoproject.com/en/6.1/topics/testing/tools/
