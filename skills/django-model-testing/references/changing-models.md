# Changing a model, and model tests that start failing

When a task changes what a model does (a new rule, a changed limit, a new field or constraint), the tests are the model's written spec, and they change with it. The risk runs both ways: a test changed to match the new code can hide a regression, and a test left asserting the old behavior blocks an intended change.

## Before the change

Run the model's existing tests and keep the result, so failures that were already there are not blamed on your change. Then find every test that asserts the behavior you are about to change: search tests, fixtures, and factories for the method, field, and constant names involved. Those tests are the old spec, and the change must update them on purpose rather than discover them by accident.

## Test first

For new or changed behavior, write the test from the new promise before touching the model, and run it to see it fail for the right reason: the assertion about the behavior, not an import error or broken setup. Then change the model and see it pass. A test written after the code tends to restate the code; one written first states what was asked for. Apply the same standard as for any model test: discriminating inputs, both sides of every boundary, the bypass paths.

## When existing tests fail after the change

Sort every failure into one of three kinds before editing anything:

- **The old spec.** The test asserts exactly the behavior the task changes. Update it to the new promise in the same change, keeping everything it covered. If a limit moves from 120 to 180, the test moves with it: 180 passes and 181 fails. Never delete it or loosen it to "no error".
- **A regression.** The test asserts something the task did not ask to change. The change broke it: fix the code, not the test.
- **A test of implementation details.** The test pinned a query string, an internal call, or an intermediate value rather than a promise. Rewrite it to assert the promise, instead of re-pinning the new details.

Change a test's expectation only when you can tie it to the requested change. List every test whose expectation changed and why: reviewers read that list as the change to the spec.

## When a model test starts failing and you did not just change the model

Find what changed before deciding anything: read the failure, then `git log -p` on the model, its abstract bases, its migrations, the settings it depends on, and recent dependency upgrades, since the test last passed. Then sort the failure into the same three kinds. An intended change updates the test and cites the commit; a regression is reported with the commit that caused it, and fixed only if the user asked for a fix; a test of implementation details is rewritten to its promise.

A test that fails only sometimes (in a different order, on another day, with other data) has a cause worth finding rather than a retry: state shared between tests outside `setUpTestData` (attributes set in `setUpClass`, module-level objects), an unpinned clock, or a queryset compared in an order it never promised because it has no `order_by()`.

## Schema and data consequences

- A change to fields or constraints needs a migration. `python manage.py makemigrations --check` exits non-zero when one is missing, without writing it.
- A new unique or check constraint can reject rows already stored in production: the migration that adds it fails on existing rows that violate it. When that can happen, the change needs a data migration that fixes those rows first, with its own test ([data-migrations.md](data-migrations.md)); say so in the report. A narrower validator does not fail a migration, but existing rows then fail `full_clean()` the next time they are edited; say so too.
- Adding a required field breaks every fixture and factory that creates the model, and renaming or removing one breaks strings rather than imports: update JSON fixtures and factories, and search field names passed as strings (`values()`, `only()`, `update_fields`, `order_by()`).

## Report

List the tests you added and confirm each failed before the change, the tests whose expectations changed with the reason for each, any regressions found, and the checks before and after.
