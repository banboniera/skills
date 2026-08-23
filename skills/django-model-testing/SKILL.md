---
name: django-model-testing
description: Write unit tests for Django model behavior — full_clean()/clean() validation, database constraints (ValidationError vs IntegrityError), custom save()/delete(), soft delete, custom managers and querysets, and transaction.on_commit(). Use whenever the user asks to test models, managers, querysets, or constraints, mentions models.py or tests under tests/models/, or asks to "add tests" for code that turns out to be a Django model. Model-layer contract only — not for DRF serializer tests (serializer.is_valid/errors) or view tests.
---

# Django Model Testing

Test **model contract** — validation rules, constraint enforcement, save/delete effects, manager scoping — never Django internals. Django ships behavior (`auto_now`, plain `CharField` max_length): trust it. Test only what model *adds*: `clean()`, validators, constraints, custom save/delete, managers, `on_commit` hooks.

## Workflow

1. **Read model and everything it touches** — fields, validators, `clean()`, `Meta.constraints`, `save()`/`delete()` overrides, custom managers/querysets, signals, `transaction.on_commit()` calls, related models. Never test code not read.
2. **Find project's model test base.** Look for existing base class before raw `TestCase` boilerplate (this codebase: `app.shared.tests.ModelTestCase` — see [Project conventions](#project-conventions)). Reuse its fixtures and assertion helpers, never hand-roll.
3. **Classify what model owns**; pick coverage from table below.
4. **Write tests**: one behavior per test, explicit setup, exact assertions. Mirror app's test path convention (`<app>/tests/models/test_<name>.py`).
5. **Run tests** for touched module only, not whole suite.

## What to cover

| Area | Do |
|------|-----|
| **Validation** | One passing `full_clean()` when model has custom validation, validators, choices, or inherited rules. One failing `full_clean()` per real invalid branch: `clean()`, cross-field rules, validators, choices, boundaries. Never assume `save()` validates — it doesn't. Pin failures to field via `message_dict`. |
| **Constraints** | Each `unique`, `UniqueConstraint`, `CheckConstraint`, one-to-one rule: validation-layer test if writes route through `full_clean()`; DB-write-failure test when database is real enforcement layer (bulk paths, race windows). Often both. Soft-delete model with unconditional unique constraint: soft-deleted row still occupies constraint, and validation checks via default manager may miss conflict DB insert hits — test that interaction (fix is condition=Q(deleted_at__isnull=True) or similar). |
| **save()** | Every custom effect: trim, normalize, derived fields, linked defaults, UUIDs, timestamps, `update_fields` when it changes outcome — state-tracking overrides (became-ready style) misfire when `update_fields` omits tracked field: test that path. `bulk_create`/`bulk_update`/`QuerySet.update()` bypass `save()` and signals entirely — callers use bulk paths: one test stating expected behavior there. After save, reload and assert **stored** values. |
| **delete()** | Custom delete: soft/hard/restore, protected paths (`ProtectedError`/`RestrictedError`), external side effects. `QuerySet.delete()` does **not** call instance `delete()` — model overrides delete: test queryset path too (or custom queryset that mirrors it). |
| **Relations** | Only where model defines behavior: cascade, `PROTECT`, `SET_NULL`, one-to-one limits, m2m state that matters, cross-model validation. |
| **Managers / querysets** | Custom methods: inclusion *and* exclusion (rows that must not appear — other tenant, soft-deleted), ordering, prefetch. Query count only if count is part of contract. |
| **Inheritance** | Shared base behavior only if concrete model's contract depends on it (soft-delete, active-only managers). |
| **Files** | Project rules: metadata, helpers, parent rules, delete behavior — not Django storage internals. |
| **on_commit** | Model uses `transaction.on_commit()`: assert with `captureOnCommitCallbacks()`. `TransactionTestCase` only if `TestCase` cannot prove it. |

**Skip:** plain field declarations with no project rule, Django internals, coverage already proven at serializer or view layer.

## Core patterns

**Builder pair — unsaved instance for validation tests, validated create for rest:**

```python
def _unsaved_order(self, **kwargs):
    attrs = {"workshop": self.workshop, "number": "RO-1", "total": Decimal("10")}
    attrs.update(kwargs)
    return RepairOrder(**attrs)

def _create_order(self, **kwargs):
    order = self._unsaved_order(**kwargs)
    order.full_clean()
    order.save()
    order.refresh_from_db()
    return order
```

**Validation — pass, and each failing branch pinned to field:**

```python
def test_valid_order_passes_full_clean(self):
    self._unsaved_order().full_clean()

def test_full_clean_rejects_closed_without_timestamp(self):
    order = self._unsaved_order(status=RepairOrder.Status.CLOSED, closed_at=None)
    with self.assertRaises(ValidationError) as ctx:
        order.full_clean()
    self.assertIn("closed_at", ctx.exception.message_dict)
```

Boundary sweeps inside `with self.subTest(value=...):` so one failing value never hides rest.

**Constraints — both layers.** Since Django 4.1 `full_clean()` also validates `Meta.constraints` (→ `ValidationError`); direct save bypasses that, hits DB (→ `IntegrityError`). `IntegrityError` breaks test's wrapping transaction — every later ORM call raises `TransactionManagementError` — so nest atomic block:

```python
def test_duplicate_number_fails_full_clean(self):
    existing = self._create_order()
    with self.assertRaises(ValidationError):
        self._unsaved_order(number=existing.number).full_clean()

def test_duplicate_number_raises_integrity_error_when_saved_without_validation(self):
    existing = self._create_order()
    with self.assertRaises(IntegrityError), transaction.atomic():
        self._unsaved_order(number=existing.number).save()
    self.assertEqual(RepairOrder.all_objects.count(), 1)  # ORM still usable
```

**save() effects — assert stored row, not Python object:**

```python
def test_save_normalizes_number(self):
    order = self._create_order(number="  ro-1 ")
    self.assertEqual(order.number, "RO-1")  # _create_order reloaded it
```

In-memory instance can differ from row (`db_default`, `update_fields` skipping field, DB-side casing) — `refresh_from_db()` before asserting persistence.

**Soft delete — flag set, default manager excludes, escape hatch still sees it:**

```python
def test_delete_soft_deletes_and_hides_from_default_manager(self):
    order = self._create_order()
    order.delete()
    order.refresh_from_db()
    self.assertIsNotNone(order.deleted_at)
    self.assertFalse(RepairOrder.objects.filter(pk=order.pk).exists())
    self.assertTrue(RepairOrder.all_objects.filter(pk=order.pk).exists())
```

**on_commit — `TestCase` never commits, so capture callbacks:**

```python
@patch("workshop.tasks.notify_order_ready.delay")
def test_ready_transition_enqueues_notification_on_commit(self, mock_delay):
    order = self._create_order()
    with self.captureOnCommitCallbacks(execute=True):
        order.status = RepairOrder.Status.READY
        order.save()
    mock_delay.assert_called_once_with(order.pk)
```

`execute=False` + invoke callbacks yourself when contract is *when* effect fires (external delete only after commit). `TransactionTestCase` only when real commit/rollback semantics are thing under test — order of magnitude slower.

## Anti-patterns

- `assertRaises(Exception)` or unpinned `assertRaises(ValidationError)` — test passes for *wrong* error. Assert field (`message_dict`) or exact exception class.
- `IntegrityError` without nested `transaction.atomic()` — poisons test transaction; every later ORM call fails confusingly.
- Testing validation through `objects.create()` — never runs `full_clean()`; proves nothing about `clean()` or validators.
- Asserting instance returned by `save()` when save normalizes or derives values — `refresh_from_db()` first.
- Per-test fixtures every test needs — use `setUpTestData` (once per class, isolated per test); mutable setup goes in test that mutates.
- `TransactionTestCase` when `captureOnCommitCallbacks()` suffices — order of magnitude slower.
- Manager tests asserting only inclusion — exclusion (other tenant, soft-deleted) usually actual contract.
- Duplicating serializer/view coverage at model layer.

## Version notes (Python 3.14, Django 6.1)

- `full_clean()` validates `Meta.constraints` since Django 4.1 (opt out per-call: `validate_constraints=False`); `save()` never validates anything.
- `CheckConstraint` takes `condition=` — `check=` kwarg removed in Django 6.0. Read constraints from `Meta` before writing tests; never guess names.
- `setUpTestData` class attributes deep-copied per test since Django 3.2; Django 6.0 **requires** deepcopyable — in-memory fixture mutation isolated, but never stash non-copyable objects (open files, connections) on class.
- Queryset comparisons: `assertQuerySetEqual` (capital S) with real objects.

## Project conventions

HuggingCar `api` project:

- Base class: `app.shared.tests.ModelTestCase` — read before writing tests; provides:
  - `assert_full_clean_raises(instance)` — expects `ValidationError`
  - `assert_integrity_error_on_second_create(create_first, create_duplicate)` — DB-layer constraint check with transaction handling
  - hard-delete, cascade, query-budget helpers (`pk_set`, `assert_get_pks_respects_budget`)
- Fixtures on `BaseTestCase`: `setup_company`, `setup_other_company`, `setup_service`, `setup_employee`, `setup_user`, `setup_user_company_detail`, … — always prefer over raw `Model.objects.create` for shared models.
- Test location mirrors model's app: `src/<app>/tests/models/test_<name>.py` (`users/tests/models/test_user.py`).
- Run: `DJANGO_ROLE=<role> rtk uv run python manage.py test <dotted.test.module> --parallel auto` from `src/`.
- Test tags: CI splits suites by role — manager runs domain apps with `--exclude-tag=worker`, worker role reruns them with `--tag=worker`. Model `on_commit` tests patch task's `.delay`, stay **untagged** (prove enqueue-on-commit, run in manager suite); `@tag("worker")` reserved for Celery task-body tests (`test_tasks.py`), outside this skill's scope.

## Quick verify (before finishing)

Meaningful validation has pass + fail `full_clean()` tests pinned to field; constraints tested at enforcing layer(s), DB-layer failures inside nested atomic; custom save/delete effects asserted after reload; delete covered on instance *and* queryset paths when overridden; managers assert exclusion, not just inclusion; `on_commit` proven via `captureOnCommitCallbacks`; tests small, independent, named by behavior.

## References

- https://docs.djangoproject.com/en/6.1/topics/testing/tools/
- https://docs.djangoproject.com/en/6.1/ref/models/constraints/
- https://adamj.eu/tech/2020/05/20/the-fast-way-to-test-django-transaction-on-commit-callbacks/
- https://adamj.eu/tech/2021/02/10/new-testing-features-in-django-3.2/
