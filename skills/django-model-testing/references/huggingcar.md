# HuggingCar api project conventions

Repo layout: Django project under `src/`, shared domain apps (`documents`, `vehicles`, `users`, `companies`) with abstract bases in `app/shared/models.py` and per-app `models/common.py`.

## Test bases (`src/app/shared/tests.py`)

Read this file before writing tests. `ModelTestCase` provides:

- `assert_full_clean_raises(instance)` — expects `ValidationError`
- `assert_integrity_error_on_second_create(create_first, create_duplicate)` — DB-layer constraint check with transaction handling
- hard-delete, cascade, and query-budget helpers (`pk_set`, `assert_get_pks_respects_budget`)

## Fixtures (`BaseTestCase`)

Always prefer over raw `Model.objects.create` for shared models:
`setup_company`, `setup_other_company`, `setup_service`, `setup_employee`, `setup_user`, `setup_user_company_detail`, `setup_supplier`, `company_data`, `generate_random_phone_number`, …

## Abstract bases

Most model behavior lives in abstract bases; test through a cheap concrete subclass (skill's Inheritance row):

- `app/shared/models.py`: `SoftDeleteModel` (cascade soft delete via `cascade_delete_root`, skip/blocking label collections), `TrackingModel`, `ActiveModel`, `UUIDModel`, commission bases.
- `vehicles/models/common.py`: `LicensePlateModel` (uppercases on `save()` and force-merges `license_plate` into `update_fields`).
- `companies/models/common.py`: `NonNegativeBalanceModel` (`MinValueValidator` on balance).

`scripts/untested_models.py` lists bases with zero test references.

## Conventions

- Test location mirrors model's app: `src/<app>/tests/models/test_<name>.py` (`users/tests/models/test_user.py`).
- Ruff ignores `PT009`/`PT027` in tests — unittest-style asserts are the convention.
- Test tags: CI splits suites by role — manager runs domain apps with `--exclude-tag=worker`; worker role reruns with `--tag=worker`. Model `on_commit` tests patch the task's `.delay` and stay **untagged** (prove enqueue-on-commit in manager suite); `@tag("worker")` is reserved for Celery task-body tests (`test_tasks.py`), outside this skill's scope.

## Cross-role coverage (deliberate duplication)

Role APIs (`manager_api`/`mechanic_api`/`customer_api`/`worker_api`) share domain models and reuse role-level classes — code born in one role (or shared apps) gets consumed by others. Rule: the origin role carries full coverage, AND **every consuming role duplicates that full coverage in its own test tree**. Never deduplicate into one place. Reason: each role's suite runs separately (`DJANGO_ROLE=<role>`), so a change to reused code must fail **immediately in every affected role's own suite** — that failure is the signal that the change has cross-role impact. Practical rules:

- Adding tests for a reused class: replicate the full test set into each role that uses it (adapted to that role's context), not just the origin role.
- Changing reused code: expect and update duplicated tests in every consuming role; a green origin suite alone proves nothing.
- Finding consumers: grep the class name across `src/*_api/` before deciding coverage scope.

## Run

From `src/`:

```
DJANGO_ROLE=<role> rtk uv run python manage.py test <dotted.test.module> --parallel auto
```

`<role>` = `manager` / `mechanic` / `customer` / `worker` — owner of changed code (`manager` default).
