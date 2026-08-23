# HuggingCar `api` project conventions

Read when writing view tests in /…/HuggingCar/api.

## Test base

`app.shared.tests.ViewTestCase` (`src/app/shared/tests.py`) — read before writing tests; provides:

- `self.factory = APIRequestFactory()` (from `setUp`)
- `build_request(method, path, data)` — unauthenticated
- `build_authenticated_request(method, path, data, user=…, company=…, employee=…)` — `force_authenticate` with `token=SimpleNamespace(company=…, employee=…)`, matching what `CompanyMixin` *and* permission classes (`IsManager`/`IsDirector` read `request.auth.employee`) expect
- `_director_request` / `_manager_request` wrappers
- Inherited `BaseTestCase` fixtures: `setup_company`, `setup_other_company`, `setup_service`, `setup_user`, `setup_employee`, `setup_user_company_detail`, `setup_director_with_detail`, `setup_manager_with_detail`, `setup_superuser_with_detail`; `assert_m2m_pks_equal`, `assert_m2m_empty`.

Always prefer these fixtures over raw `Model.objects.create` for shared models.

## Shared view architecture

Views compose bases from `app/shared/views.py` + `app/shared/mixins.py` — concrete view contract includes inherited behaviors:

| Base/mixin | Adds |
|------------|------|
| `BaseViewSet` | pagination validation in `list` |
| `FormListViewSet` | serializer mapped by action |
| `DocumentViewSet` | date-range params + status-only write responses |
| `ByPksActionMixin` | `POST …/by-pks`, capped at 100 IDs |
| `SelectAllMixin` | `GET …/all`, capped at 1000 |
| `CompanyM2MMixin` | add-to-company / remove-from-company |
| `SoftDeleteRestoreMixin` | `POST …/{pk}/restore` |
| `FileViewSet` | `confirm` / `download` actions |

## Auth

Role settings pick auth class (`CompanyTokenAuthentication` manager, `CustomerTokenAuthentication` customer; both Knox-based) — anonymous `401`, wrong role `403`. Customer-api tests exercising auth flow itself: login `POST /auth/login/`, then `client.credentials(HTTP_AUTHORIZATION="Token " + token)`.

Permission roles (`app/permissions.py`): `IsManager` passes for manager, director, **and** superuser; `IsDirector` for director + superuser. All read `request.auth.employee` via `_get_employee`, which returns `None` when the token lacks an employee — then permission fails **before** the `is_superuser` check. Superuser tests must use `setup_superuser_with_detail` and pass `employee` in the token; `is_superuser` alone still gets `403`. "Every allowed role" for a manager endpoint = manager, director, superuser; rejected = plain employee (`403`), anonymous (`401`).

## Paths & running

- Test path mirrors view: `src/<role_api>/<app>/tests/views/test_<name>.py`.
- Run from `src/`: `DJANGO_ROLE=<role> uv run python manage.py test <dotted.test.module> --parallel auto` (`role` = `manager`/`mechanic`/`customer`/`worker`, owner of changed code).
- CI uses `app.settings.ci`: in-memory sqlite, no migrations, MD5 hasher, eager Celery.
