# HuggingCar api project conventions

Repo layout: Django project under `src/`, role-split APIs (`manager_api`, `mechanic_api`, `customer_api`) over shared domain apps (`documents`, `vehicles`, `users`, `companies`).

Stack (from `src/uv.lock`): Python 3.14, Django 6.1, DRF 3.18.0, django-filter 26.1, django-rest-knox 5.1.

## Test bases (`src/app/shared/tests.py`)

Read this file before writing tests. `SerializerTestCase` provides:

- `assert_valid_save(serializer)` — asserts valid (errors as failure message) + saves, returns instance
- `assert_serializer_error(serializer, key, exact_message=…, message_fragment=…)` — fails validation, asserts key, structure, and message
- `assert_validation_fails_with_key(serializer, key)` / `assert_validation_fails_with_key_and_structure(serializer, key)` / `assert_validation_fails_with_keys(serializer, keys)`
- `assert_data_has_exact_keys(data, keys)` — exact `.data` key set
- `assert_saved_field_map(instance, {field: value})` — `refresh_from_db` + persisted field map
- `assert_partial_update_result(serializer, expected_changed, expected_unchanged)` — save + field diff
- `build_serializer_request_context(company, user=…, employee=…)` — request-like object for `context={"request": …}`; sets `request.auth.company`, `request.auth.employee`, `request.user`

App-level serializer test bases exist too (e.g. `manager_api/documents/tests/serializers/service_order/base.py` → `ServiceOrderSerializerTestCase` with company/service/employee/vehicle/service-order graph prebuilt). Check sibling test dirs first; inherit the closest base.

## Fixtures (`BaseTestCase`)

Always prefer over raw `Model.objects.create` for shared models:
`setup_company`, `setup_other_company`, `setup_service`, `setup_other_service`, `setup_employee`, `setup_user`, `setup_user_company_detail`, `setup_supplier`, `setup_superuser_with_detail`, `setup_director_with_detail`, `setup_manager_with_detail`, `generate_random_phone_number`, `company_data`.

Employee flags matter for scoped querysets: `is_manager=True` / `is_mechanic=True` (`setup_employee({"service": …, "modified_by": …, "is_manager": True})`).

## Conventions

- Test location mirrors serializer: `src/<role_api>/<app>/tests/serializers/test_<name>.py`.
- Cross-company scoping is the core security contract: most writable relations use `Model.objects.get_pks(company_pk)` querysets set in `__init__` from context. Always test in-scope pass + out-of-scope fail.
- Translated fields (`en`/`es`/`pl`/`ru`) resolve via context user language (`LanguageCode`); assert representation per language when output translated.
- Serializer-level query budgets are an established convention: wrap `.data` in `assertNumQueries(N)`; prefetched instance gets `assertNumQueries(0)` (precedent: `manager_api/vehicles/tests/serializers/test_vehicle.py`).
- Ruff ignores `PT009`/`PT027` in tests — unittest-style asserts are the convention.

## Cross-role coverage (deliberate duplication)

Role APIs (`manager_api`/`mechanic_api`/`customer_api`/`worker_api`) reuse serializers across roles — a serializer born in one role (or `app/shared`) gets consumed by others. Rule: the origin role carries full coverage, AND **every consuming role duplicates that full coverage in its own test tree**. Never deduplicate into one place. Reason: each role's suite runs separately (`DJANGO_ROLE=<role>`), so a change to reused code must fail **immediately in every affected role's own suite** — that failure is the signal that the change has cross-role impact. Practical rules:

- Adding tests for a reused serializer: replicate the full test set into each role that uses it (adapted to that role's auth/context), not just the origin role.
- Changing reused code: expect and update duplicated tests in every consuming role; a green origin suite alone proves nothing.
- Finding consumers: grep the class name across `src/*_api/` before deciding coverage scope.

## Run

From `src/`:

```
DJANGO_ROLE=<role> rtk uv run python manage.py test <dotted.test.module> --parallel auto
```

`<role>` = `manager` / `mechanic` / `customer` / `worker` — owner of changed code (`manager` default).
