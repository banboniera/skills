---
name: django-model-testing
description: Write unit tests for Django model behavior — full_clean()/clean() validation, database constraints (ValidationError vs IntegrityError), custom save()/delete(), soft delete, custom managers and querysets, and transaction.on_commit(). Use whenever the user asks to test models, managers, querysets, or constraints, mentions models.py or tests under tests/models/, or asks to "add tests" for code that turns out to be a Django model. Model-layer contract only — not for DRF serializer tests (serializer.is_valid/errors) or view tests.
---

# Django Model Testing

Test **model contract** — validation rules, constraint enforcement, save/delete effects, manager scoping — never Django internals. Django ships behavior (`auto_now`, plain `CharField` max_length): trust it. Test only what model *adds*: `clean()`, validators, constraints, custom save/delete, managers, `on_commit` hooks.

## Workflow

1. **Read model and everything it touches** — fields, validators, `clean()`, `Meta.constraints`, `save()`/`delete()` overrides, custom managers/querysets, signals, `transaction.on_commit()` calls, related models. Never test code not read.
2. **Find project's model test base.** Look for existing base class before raw `TestCase` boilerplate; reuse its fixtures and assertion helpers, never hand-roll. Project-specific conventions (bases, fixtures, run command): read `references/` — see Bundled resources.
3. Coverage gaps unknown? Run `scripts/untested_models.py <project-src-dir>` — lists model classes no test references (abstract bases show up here; test them through a concrete subclass).
4. **Classify what model owns**; pick coverage from table below. `scripts/coverage_map.py <models.py> [Class]` prints per-class checklist — validators, save/delete overrides, constraints, branching properties, `on_commit` — mapped to required tests.
5. **Write tests**: one behavior per test, explicit setup, exact assertions. Mirror app's test path convention (`<app>/tests/models/test_<name>.py`).
6. **Run tests** for touched module only, not whole suite.

**Batch coverage** (many untested models, subagents available): shard by MODULE, one subagent per module — never per class (abstract bases + their concrete subclasses belong to one worker). Each subagent brief: this SKILL.md path + target module + output test path; workers write tests only — syntax check (`ast.parse`) at most; never run suite/linters mid-batch. Orchestrator merges, then runs new test modules **serially** at the end — concurrent `manage.py test` invocations collide on the shared `test_<dbname>` database. No subagents: work through gap list module by module, same rule.

## What to cover

| Area | Do |
|------|-----|
| **Validation** | One passing `full_clean()` when model has custom validation, validators, choices, or inherited rules. One failing `full_clean()` per real invalid branch: `clean()`, cross-field rules, validators, choices, boundaries. `save()` never validates: validator-guarded field gets one test documenting the bypass (invalid value saves raw without `full_clean()`) — pins the trust boundary callers rely on. Pin failures to field via `message_dict`. |
| **Constraints** | Each `unique`, `UniqueConstraint`, `CheckConstraint`, one-to-one rule: validation-layer test if writes route through `full_clean()`; DB-write-failure test when database is real enforcement layer (bulk paths, race windows). Often both. Soft-delete model with unconditional unique constraint: soft-deleted row still occupies constraint, and validation checks via default manager may miss conflict DB insert hits — test that interaction (fix is condition=Q(deleted_at__isnull=True) or similar). |
| **save()** | Every custom effect: trim, normalize, derived fields, linked defaults, UUIDs, timestamps, `update_fields` when it changes outcome — state-tracking overrides (became-ready style) misfire when `update_fields` omits tracked field: test that path. `bulk_create`/`bulk_update`/`QuerySet.update()` bypass `save()` and signals entirely — callers use bulk paths: one test stating expected behavior there. After save, reload and assert **stored** values. |
| **delete()** | Custom delete: soft/hard/restore, protected paths (`ProtectedError`/`RestrictedError`), external side effects. `QuerySet.delete()` does **not** call instance `delete()` — model overrides delete: test queryset path too (or custom queryset that mirrors it). |
| **Relations** | Only where model defines behavior: cascade, `PROTECT`, `SET_NULL`, one-to-one limits, m2m state that matters, cross-model validation. |
| **Managers / querysets** | Custom methods: inclusion *and* exclusion (rows that must not appear — other tenant, soft-deleted), ordering, prefetch. Query count only if count is part of contract. |
| **Computed reads** | Properties/methods with branching or calculation: read contract — test boundaries. Trivial delegation (`return self.x`): skip. `GeneratedField`/`db_default`: DB computes value — assert **after** `refresh_from_db()`, never on in-memory instance. Annotations encoding business rules: assert resulting rows/values, never SQL text. |
| **Inheritance** | Shared base behavior only if concrete model's contract depends on it (soft-delete, active-only managers). |
| **Files** | Project rules: metadata, helpers, parent rules, delete behavior — not Django storage internals. |
| **on_commit** | Model uses `transaction.on_commit()`: assert with `captureOnCommitCallbacks()`. `TransactionTestCase` only if `TestCase` cannot prove it. |
| **Signals** | Receivers the app registers on model: trigger action, assert **effect** (row/state change); complex receiver: test function directly + one test proving connection. Bulk paths (`bulk_create`, `QuerySet.update()`) never fire save signals — receiver's effect load-bearing: test the bypass path expectation too. Fixture noise: disconnect/mute receivers around setup, never globally. |

**Skip:** plain field declarations with no project rule, Django internals, coverage already proven at serializer or view layer.

## Core patterns

**Class fixtures + builder pair — `setUpTestData` for shared rows, unsaved instance for validation tests, validated create for rest:**

```python
@classmethod
def setUpTestData(cls):  # once per class; per-test isolation via deepcopy
    cls.workshop = cls.setup_workshop()

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
- `GeneratedField` (Django 5.0+) and `db_default`: value computed by database — in-memory instance stale until `refresh_from_db()`.
- `setUpTestData` class attributes deep-copied per test since Django 3.2; Django 6.0 **requires** deepcopyable — in-memory fixture mutation isolated, but never stash non-copyable objects (open files, connections) on class.
- Queryset comparisons: `assertQuerySetEqual` (capital S) with real objects.

## Bundled resources

- `scripts/coverage_map.py` — per-class checklist of validators, overrides, constraints, properties mapped to required tests. Usage: `python scripts/coverage_map.py path/to/models.py [ClassName]`.
- `references/huggingcar.md` — HuggingCar api project: `ModelTestCase` helpers, fixtures, untested abstract bases, test tags, paths, run command. Read when working in that repo.
- `scripts/untested_models.py` — print model classes unreferenced by any test. Usage: `python scripts/untested_models.py /path/to/project/src`.

## Quick verify (before finishing)

Meaningful validation has pass + fail `full_clean()` tests pinned to field; constraints tested at enforcing layer(s), DB-layer failures inside nested atomic; custom save/delete effects asserted after reload; delete covered on instance *and* queryset paths when overridden; managers assert exclusion, not just inclusion; branching properties and `GeneratedField`/`db_default` asserted after reload; registered receivers proven by effect (bypass paths stated); `on_commit` proven via `captureOnCommitCallbacks`; tests small, independent, named by behavior.

## References

- https://docs.djangoproject.com/en/6.1/topics/testing/tools/
- https://docs.djangoproject.com/en/6.1/ref/models/constraints/
- https://adamj.eu/tech/2020/05/20/the-fast-way-to-test-django-transaction-on-commit-callbacks/
- https://adamj.eu/tech/2021/02/10/new-testing-features-in-django-3.2/
