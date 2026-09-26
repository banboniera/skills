---
name: drf-serializer-testing
description: Writes, maintains, and reviews unit tests for Django REST Framework serializers across their lifecycle so the tests catch real regressions — covering existing serializers, changing a serializer's validation, save logic, or output (the API contract) test-first, deciding what to do when a serializer test starts failing (including after a DRF upgrade), and reviewing existing serializer tests. Covers validation, uniqueness, create/update/partial update, nested and many=True writes, exact output shape, tenant-scoped related fields, and query counts while serializing. Use whenever a task writes, reviews, updates, or fixes tests for DRF serializers, and whenever it adds a serializer or changes one's fields, validation, save logic, or output, since the tests change with it. Also use for an "add tests" request on code that turns out to be a DRF serializer, a failing serializer test, or a question about what existing serializer tests miss. Not for model tests or view tests (permissions, routing, status codes).
---

# Testing DRF serializers

A serializer is an API contract: which input it accepts, what it stores, and what it returns. A serializer test exists to fail when that contract breaks. Coverage does not show that: a test can run every line and still pass when the logic is wrong, because it asserts too little or asserts what the code happens to do. Every task below uses the standard in this file; read the reference that matches the task too.

| Task | Read |
| --- | --- |
| Add tests for serializers that already exist | this file |
| Add or change serializer behavior or output, or a serializer test starts failing | this file and [references/changing-serializers.md](references/changing-serializers.md) |
| Review existing serializer tests | this file and [references/reviewing.md](references/reviewing.md) |

## The standard

A good serializer test states one rule the serializer promises, sets up the smallest case where that rule makes a visible difference, and asserts the outcome exactly. Before keeping a test, ask: if someone deleted or inverted the code behind this rule, would this test fail? If not, it is decoration.

That question drives the choices below.

- **Expected values come from the promise, not the code.** The promise is what the serializer's docstring, field names, and callers say it does, and what its clients rely on. Reading the implementation and asserting what it returns only proves the code equals itself, and it passes on the bug. When the promise and the code disagree, you have found a bug (see "When a test exposes a bug").
- **Break one thing per invalid payload.** Start from one valid payload and change a single field per test. A payload that is invalid in two ways keeps the test passing when the rule it names breaks, and cross-field rules in `validate()` never run at all while any field is invalid.
- **Inputs must discriminate.** Use input the rule changes: lowercase text for an uppercasing validator, the exact boundary value and the first value past it, a related object from each side of a queryset filter, a value that rounds differently for a rounding rule.
- **Assert the exact error.** Pin the key and the code: `serializer.errors["assignee"][0].code == "does_not_exist"`. `assertFalse(serializer.is_valid())` alone passes on any error, including the wrong one.
- **Assert stored state and exact output.** After `save()`, reload with `refresh_from_db()` or query again, and assert every effect, including related rows. For output, assert the whole key set and each value as a client sees it.
- **Assert what must not happen.** An out-of-scope id rejected, a write-only field absent from output, no rows written by invalid input, fields and related rows left alone by a partial update. Exclusion is usually where the bugs are.

## Find the promise

Read the serializer and everything that gives it behavior before writing anything: declared fields, `Meta` (`fields`, `exclude`, `read_only_fields`, `extra_kwargs`, `validators`), the model fields it derives from (`max_length`, `choices`, validators, `unique`, constraints), `__init__` (querysets or fields set from context), `validate_<field>()`, `validate()`, `create()`, `update()`, `to_internal_value()` and `to_representation()` overrides, `SerializerMethodField` methods, nested serializers, and custom `ListSerializer` classes. Then read its callers: which views use it, with which context, whether they update partially, which queryset they pass (and what it prefetches), and which keyword arguments they pass to `save()`. As you read, compare each rule's promise with what its code does.

Follow the project's testing conventions: its base test classes, fixture and assertion helpers, context builders, factories, file layout, and test command. Look in AGENTS.md or CLAUDE.md, neighboring serializer tests, and CI config, and reuse what exists rather than hand-rolling setup.

Test what the project added, not DRF: skip a plain `CharField` rejecting `None` or an `IntegerField` rejecting `"abc"`. A limit or choice list the project configured is its own rule and gets a boundary test. Leave permissions, routing, status codes, and the view's own queryset to view tests.

## Behaviors and their traps

**Validation order.** For each field, DRF runs the field's own checks and validators, then `validate_<field>()`, and skips `validate_<field>()` when the field already failed. Only when every field passed does it run the serializer's `validators` (such as unique-together checks) and then `validate()`. `ValidationError("...")` raised in `validate()` lands under `non_field_errors`; a dict lands under its keys. DRF's own codes include `required`, `null`, `blank`, `invalid`, `invalid_choice`, `max_length`, `min_value`, `max_value`, `does_not_exist`, `incorrect_type`, and `unique`; a project `ValidationError` raised without a code gets `invalid`, so pin its message instead.

**What ModelSerializer copies, and what it never checks.** It copies the model field's `max_length`, `choices`, validators, `null` (as `allow_null`), and `blank` (as `allow_blank`). It never calls the model's `full_clean()` or `clean()`, and never checks a `CheckConstraint` or a `UniqueConstraint` built from expressions (such as `Lower("name")`): those fail as an `IntegrityError` at save, a server error for the client. Test such a rule here only when the serializer takes it on; otherwise name it in the report.

**Uniqueness.** `ModelSerializer` adds unique validators for `unique=True`, `unique_together`, and `UniqueConstraint(fields=...)`, including conditional ones, with the code `unique` (a multi-field constraint's `violation_error_code` replaces it), under the field for a single field and under `non_field_errors` for several. Declaring `Meta.validators` replaces them rather than adding to them. It adds none when a field of the constraint is not writable: excluded from `fields`, or read-only without a default, as with a tenant field passed through `save(company=...)`. Then `is_valid()` passes and `save()` raises `IntegrityError`, unless a hand-written check covers it. Test uniqueness where writes meet it: create the conflicting row first and expect a validation error on the right key; allow the same value in another tenant or outside the constraint's condition; and update a row sending its own value back unchanged, as a full update or a form resubmitting every field does, which a hand-written check that forgets to exclude `self.instance` wrongly rejects. A validator runs only for fields sent, so a partial update that leaves the field out proves nothing here.

**Related fields and scope.** A related field whose queryset is narrowed from context (to the request's company, to active rows) is a security boundary. Test that an in-scope id passes and that an id from each excluded category (another tenant, inactive, deleted) fails with `does_not_exist`, on create and on update, since code can narrow the queryset on one path only. Check every related field, including those inside nested serializers and the `child_relation` of a `many=True` related field.

**Writes: create, update, partial update.** A writable `ModelSerializer`'s create and full update are its write contract even without custom methods. With `partial=True`, required fields are skipped, field defaults are not applied, and `validate()` receives only the fields sent (an explicit `null` is sent; an omitted key is not), so a rule combining fields must fall back to the instance's stored values; test each such rule through a partial update. Test that a partial update leaves unsent fields and related rows alone: code that treats a missing nested key as an empty list deletes every child. A full update applies defaults again: a `HiddenField(default=CurrentUserDefault())` reassigns the owner on every full update unless wrapped in `CreateOnlyDefault`, so test the owner through a full update by a different user; a partial update never applies defaults and passes either way. Test the `save(**kwargs)` path the view uses, since those values override validated data. Read-only fields and unknown keys in input are silently ignored: test that sending a field the client must not set, such as the owner or tenant, changes nothing. Invalid input must leave the database unchanged.

**Nested writes and many=True.** `ModelSerializer`'s default `create()` and `update()` refuse writable nested fields, so nested writes are always custom code: test create with children, and an update that changes, adds, and omits children, a child id that belongs to another parent, and a partial update without the nested key. A nested serializer's errors are a dict under its key. Since DRF 3.18, `many=True` errors are a dict keyed by the index of each invalid item only: `serializer.errors["lines"][1]["quantity"]`. Older versions returned a list with `{}` for valid items, and `LIST_SERIALIZER_ERRORS_AS_DICT = False` restores that, deprecated. A plain `many=True` serializer creates many objects but refuses to update them unless its `ListSerializer` defines `update()`; it accepts an empty list unless `allow_empty=False`.

**Output.** Assert the exact key set, `assertEqual(set(data), {...})`, so that a key added by accident (a leak) or removed (a client break) fails. Write-only fields must be absent. Assert values as clients receive them: `DecimalField` output is a string (`"12.50"`), datetimes are ISO 8601 in the current time zone, and a null value is a key present with `None`, which clients treat differently from a missing key. Test computed values (`SerializerMethodField`, `to_representation()`) at their boundaries, such as rounding, against literal expected values rather than values recomputed with the code's own formula.

**Context.** For each branch of behavior that reads `self.context` (the request's user, tenant, or language), test with the context the callers pass. A missing context matters only if a caller omits it; `CurrentUserDefault` without a request raises `KeyError`, not a validation error.

**Query count.** DRF never prefetches: related fields, nested serializers, and method fields query once per row unless the caller's queryset prefetched. When the serializer promises to work from prefetched data, serialize at least two prefetched rows inside `assertNumQueries(0)`, or the exact number it may run. Never pin a count measured on an unprefetched queryset, which locks the N+1 in. On a prefetched relation, `.all()`, `.count()`, and `.exists()` use the prefetch cache, but `.filter()`, `.order_by()`, and `.first()` query again.

**Time.** A rule that compares with the current time (a start in the future, an expiry) needs a pinned clock: patch `timezone.now` where the serializer looks it up, or use the project's time-machine or freezegun, and test the exact instant of the boundary and the first instant past it. With a live clock, "one hour ago" and "tomorrow" pass whether the rule uses `<` or `<=`.

**Output caching.** `serializer.data` is computed once and cached, and `save()` after reading `.data` raises `AssertionError`. To see output after a change, build a new serializer.

## Writing the tests

```python
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from tracker.models import Member, Task, Team
from tracker.serializers import TaskListSerializer, TaskSerializer


class TaskSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):  # shared rows, created once; each test sees its own deep copy
        cls.team = Team.objects.create(name="Core")
        cls.ada = Member.objects.create(team=cls.team, name="Ada")
        cls.outsider = Member.objects.create(team=Team.objects.create(name="Other"), name="Eve")

    def setUp(self):
        self.context = {"request": SimpleNamespace(user=None, team=self.team)}  # what the view passes

    def _serializer(self, instance=None, partial=False, **fields):
        data = fields if partial else {"title": "Fix login", "assignee": self.ada.pk, "estimate_hours": "1.5"} | fields
        return TaskSerializer(instance, data=data, partial=partial, context=self.context)

    def test_assignee_from_another_team_is_rejected(self):
        serializer = self._serializer(assignee=self.outsider.pk)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(serializer.errors["assignee"][0].code, "does_not_exist")
        self.assertFalse(Task.objects.exists())

    def test_marking_done_without_assignee_is_rejected(self):
        task = Task.objects.create(team=self.team, title="Fix", estimate_hours=1)
        serializer = self._serializer(task, partial=True, status="done")
        self.assertFalse(serializer.is_valid())
        self.assertEqual(serializer.errors["non_field_errors"][0].code, "done_without_assignee")

    def test_partial_update_keeps_fields_not_sent(self):
        task = Task.objects.create(team=self.team, title="Old", assignee=self.ada, estimate_hours=2)
        serializer = self._serializer(task, partial=True, title="New")
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        task.refresh_from_db()
        self.assertEqual((task.title, task.assignee, task.estimate_hours), ("New", self.ada, Decimal("2.00")))

    def test_output_is_exactly_the_public_fields(self):
        task = Task.objects.create(team=self.team, title="Fix", estimate_hours=Decimal("1.5"), private_note="secret")
        data = TaskSerializer(task, context=self.context).data
        self.assertEqual(set(data), {"id", "title", "status", "assignee", "estimate_hours"})
        self.assertEqual((data["estimate_hours"], data["assignee"]), ("1.50", None))

    def test_list_serializes_prefetched_rows_without_queries(self):
        for title in ("A", "B"):
            Task.objects.create(team=self.team, title=title, assignee=self.ada, estimate_hours=1)
        tasks = list(Task.objects.select_related("assignee").order_by("title"))
        with self.assertNumQueries(0):
            data = TaskListSerializer(tasks, many=True).data
        self.assertEqual([row["assignee_name"] for row in data], ["Ada", "Ada"])
```

- Instantiate the serializer directly, with the context its callers pass; going through a view or test client mixes in authentication, permissions, and routing, and hides which layer broke.
- On the valid path, `self.assertTrue(serializer.is_valid(), serializer.errors)` shows the errors when it fails. Avoid `is_valid(raise_exception=True)` on the invalid path, since the error structure is what you assert.
- Put rows most tests share in `setUpTestData`; its attributes must support `copy.deepcopy`. Create what a test changes inside that test.
- Name each test after the rule it checks, so a failure reads as the broken promise.

## When a test exposes a bug

If a test written from the promise fails because the serializer breaks it, keep the test as written and failing, leave the serializer unchanged, and finish the rest. Never add a test that asserts behavior you believe is wrong. In your report, name the failing test, the input, and what the promise says, so the user can decide whether to fix the serializer. This applies to bugs you find; a change the user asked for follows [references/changing-serializers.md](references/changing-serializers.md).

## Finish

Run the new or changed tests with the project's test command, limited to the modules you touched. They pass, except tests you kept because they expose a bug.

Report what you tested, the bugs found with their failing tests, and anything the tests cannot prove, such as a database constraint no serializer checks, which reaches clients as a server error.

To find serializers no test mentions at all, when covering a whole app or reviewing, search the test files for each serializer class name; a serializer tested only through a parent that nests it can look untested.

For many serializers at once with subagents, give each subagent a whole module, since sibling serializers share bases and fixtures, and have them write tests only; run the new test modules one at a time at the end, because parallel `manage.py test` runs can collide on a shared test database.
