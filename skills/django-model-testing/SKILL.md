---
name: django-model-testing
description: Writes, maintains, and reviews unit tests for Django models across their lifecycle so the tests catch real regressions — covering existing models, changing a model's behavior test-first, deciding what to do when a model test starts failing, testing data migrations (RunPython), and reviewing existing model tests. Covers validation (full_clean, clean, validators), constraints, custom save()/delete(), soft delete, managers and querysets, signals, and transaction.on_commit. Use whenever a task writes, reviews, updates, or fixes tests for Django models, managers, querysets, or data migrations, and whenever it changes a Django model's behavior (a rule, limit, field, or constraint in models.py), since the model's tests change with it. Also use for an "add tests" request on code that turns out to be a Django model, a failing model test, or a question about what existing model tests miss or get wrong. Not for DRF serializer or view tests.
---

# Testing Django models

A model test exists to fail when the model's behavior breaks. Coverage does not show that: a test can run every line and still pass when the logic is wrong, because it asserts too little or asserts what the code happens to do. Every task below uses the standard in this file; read the reference that matches the task too.

| Task | Read |
| --- | --- |
| Add tests for models that already exist | this file |
| Add or change model behavior, or a model test starts failing | this file and [references/changing-models.md](references/changing-models.md) |
| Test a data migration (`RunPython`) | this file and [references/data-migrations.md](references/data-migrations.md) |
| Review existing model tests | this file and [references/reviewing.md](references/reviewing.md) |

## The standard

A good model test states one rule the model promises, sets up the smallest case where that rule makes a visible difference, and asserts the outcome exactly. Before keeping a test, ask: if someone deleted or inverted the code behind this rule, would this test fail? If not, it is decoration.

That question drives the choices below.

- **Expected values come from the promise, not the code.** The promise is what the method's name, docstring, and callers say it does. Reading the implementation and asserting what it returns only proves the code equals itself, and it passes on the bug. When the promise and the code disagree, you have found a bug (see "When a test exposes a bug").
- **Inputs must discriminate.** Use input the rule changes: lowercase text for an uppercasing save, the exact boundary value and the first value past it for a limit, a row on each side of a queryset filter or a constraint's condition. Input that already satisfies the rule tests nothing.
- **Assert stored state.** Reload with `refresh_from_db()` or query again before asserting what was saved; the in-memory instance can differ from the row.
- **Assert the exact failure.** Pin a `ValidationError` to its key (and its code when callers branch on it), and an exception to its class. A bare `assertRaises(ValidationError)` or `assertRaises(Exception)` passes on the wrong error.
- **Assert what must not happen too.** Rows a queryset must leave out, a notification a save must not send, a field a partial save must not lose. Exclusion is usually where the bugs are.

## Find the promise

Read the model and everything that gives it behavior before writing anything: fields and validators, `clean()`, `Meta.constraints`, `save()` and `delete()` overrides, managers and querysets, abstract bases in other modules, signal receivers (usually `signals.py`, connected in `apps.py`), `transaction.on_commit()` calls, and the code that calls the model, especially bulk writes and partial saves. As you read, compare each method's promise with what its code does.

Follow the project's testing conventions: its base test classes, fixture and assertion helpers, factories, file layout, tags, and test command. Look in AGENTS.md or CLAUDE.md, the tests of neighboring models, and CI config, and reuse what exists rather than hand-rolling setup.

Test what the project added, not Django: skip plain fields, `max_length`, `auto_now`, and foreign keys that merely exist.

## Behaviors and their traps

**Validation.** `save()` never validates; only `full_clean()` does, running `clean_fields()`, then `clean()`, then `validate_unique()`, then `validate_constraints()`, and merging all errors into one `ValidationError`. Test validation on an unsaved instance through `full_clean()`: one passing case, then one failing case per rule, each pinned to its key in `message_dict`. When `save()` normalizes a field (trims, uppercases) that a validator or constraint checks, validation runs on the raw value first: test that a duplicate typed differently is still caught.

**Constraints.** Test each constraint where writes actually meet it: through `full_clean()` when writes are validated, and as an `IntegrityError` on save when the database is the guard (bulk writes, races). Constraint errors from `full_clean()` land under `NON_FIELD_ERRORS`, except a single-field unique constraint, which lands under its field. Pin the key and the code: a conditional or check constraint reports its `violation_error_code`, but a unique constraint on plain fields reports Django's own `unique` or `unique_together` code unless it also sets a custom message, so confirm the code by running the violation once. For a conditional constraint (`condition=Q(...)`), test both sides: the conflict it forbids, and the same values allowed where the condition does not hold. Database-specific behavior, such as `nulls_distinct`, is enforced only by the database that supports it; if tests run on a different backend than production, say which constraints the tests cannot prove.

**save() overrides.** Assert each effect on the stored row. Partial saves are where overrides break: when a field the override changes or reacts to is left out of `update_fields`, the change may never be written, and an effect keyed to a change, such as a notification when a status becomes ready, may fire for a value that was never saved. Test that path. `bulk_create()`, `bulk_update()`, and `QuerySet.update()` skip `save()` and signals; when callers use them, add a test stating what happens there.

**delete(), soft delete, restore.** Read which rows are removed and which are only marked, and test every branch: hard delete, soft delete, what blocks it (`ProtectedError`, `RestrictedError`, related rows), what cascades, and `restore()`. Test how deleted rows stay out of reads: through the default manager, a second manager, or a queryset method. Reverse relations (`parent.children.all()`) use the default manager's class, so they hide deleted rows only if that manager does; a forward foreign key or one-to-one (`child.parent`) uses the base manager and returns a deleted row anyway. `QuerySet.delete()` never calls the instance's `delete()`: when the model overrides `delete()`, test the queryset path, and whether a custom queryset mirrors the override.

**Managers and querysets.** For each custom method, assert both the rows it returns and the rows it must leave out, such as another tenant's, closed, or deleted rows. Build the data so every excluded category is present. Test chaining when callers chain (`Model.objects.alive().for_company(c)`), and query counts only when a budget is part of the contract.

**Signals.** Trigger the model action and assert the receiver's effect on stored state. For a complex receiver, test the function directly plus one test proving it is connected. When fixture setup fires receivers you are not testing, silence them around that setup only.

**on_commit.** `TestCase` wraps each test in a transaction that never commits, so `on_commit` callbacks never run on their own, and a test that does not capture them passes even when the callback is broken. Patch what the callback calls, capture with `captureOnCommitCallbacks()`, assert nothing ran yet, then run the captured callbacks and assert the effect: that proves both the effect and that it waits for the commit. Also test a save that must queue nothing, such as one that does not make the transition. Use `TransactionTestCase` only when real commit or rollback behavior is what you are testing.

**Generated and database values.** `GeneratedField`, `db_default`, and expression-assigned values are computed by the database. Assert them after `refresh_from_db()`, and for an annotation that encodes a business rule, assert the resulting values, never the SQL.

**Time.** A rule that depends on the current time needs a pinned clock, or the test drifts across midnight, month ends, and time zones. Use the project's tool (time-machine, or freezegun if that is what it uses), or patch `django.utils.timezone.now` if it has none, and set the clock right at the boundary the rule cares about.

**Properties and methods.** Test those that branch or calculate, at their boundaries; skip plain delegation such as returning a field.

**Abstract bases.** Test a base's behavior through a concrete model that uses it, preferably a real subclass the project already has; an abstract model has no table.

## Writing the tests

```python
from unittest.mock import patch

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from shop.models import Order, Shop


class OrderTests(TestCase):
    @classmethod
    def setUpTestData(cls):  # shared rows, created once; each test sees its own deep copy
        cls.shop = Shop.objects.create(name="Main")

    def _order(self, **fields):  # unsaved, for validation tests
        return Order(**{"shop": self.shop, "number": "ro-1"} | fields)

    def test_closed_order_requires_closed_at(self):
        with self.assertRaises(ValidationError) as ctx:
            self._order(status=Order.Status.CLOSED, closed_at=None).full_clean()
        self.assertIn("closed_at", ctx.exception.message_dict)

    def test_number_is_unique_per_shop(self):
        Order.objects.create(shop=self.shop, number="RO-1")
        with self.assertRaises(ValidationError) as ctx:
            self._order(number="RO-1").full_clean()
        self.assertEqual(ctx.exception.error_dict[NON_FIELD_ERRORS][0].code, "unique_together")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.create(shop=self.shop, number="RO-1")

    def test_save_stores_number_uppercase(self):
        order = Order.objects.create(shop=self.shop, number="ro-2")
        order.refresh_from_db()
        self.assertEqual(order.number, "RO-2")

    @patch("shop.models.notify_ready.delay")
    def test_becoming_ready_notifies_after_commit(self, notify):
        order = Order.objects.create(shop=self.shop, number="RO-3")
        with self.captureOnCommitCallbacks() as callbacks:
            order.status = Order.Status.READY
            order.save()
        notify.assert_not_called()
        for callback in callbacks:
            callback()
        notify.assert_called_once_with(order.pk)
```

- Wrap every expected `IntegrityError` in `transaction.atomic()`: without it the failed statement breaks the test's transaction and every later query fails.
- Put rows most tests share in `setUpTestData`; its attributes must support `copy.deepcopy`. Create what a test changes inside that test.
- Compare querysets with `assertQuerySetEqual`, or sets of primary keys when order does not matter.
- Name each test after the rule it checks, so a failure reads as the broken promise.

## When a test exposes a bug

If a test written from the promise fails because the model breaks it, keep the test as written and failing, leave the model unchanged, and finish the rest. Never add a test that asserts behavior you believe is wrong. In your report, name the failing test, the input, and what the promise says, so the user can decide whether to fix the model. This applies to bugs you find; a model change the user asked for follows [references/changing-models.md](references/changing-models.md).

## Finish

Run the new or changed tests with the project's test command, limited to the modules you touched. They pass, except tests you kept because they expose a bug.

Report what you tested, the bugs found with their failing tests, and anything the tests cannot prove, such as constraints the test database does not enforce.

To find models no test mentions at all, when covering a whole app or reviewing, run this skill's `scripts/untested_models.py <src-dir>`. It matches names only, so an abstract base appears even when its subclasses are tested.

For many models at once with subagents, give each subagent a whole module, since an abstract base and its subclasses belong together, and have them write tests only; run the new test modules one at a time at the end, because parallel `manage.py test` runs can collide on a shared test database.
