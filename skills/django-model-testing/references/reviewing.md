# Reviewing model tests

Read the models first, then the tests, and judge the tests against the standard in SKILL.md: would each one fail if the rule it names broke? Passing tests prove nothing by themselves; the review is about what they would miss.

## What to look for

Rank findings by how likely each is to let a real regression through:

1. **False greens.** Tests that cannot fail: `on_commit` effects that never run because the callbacks were not captured, assertions that also accept the broken outcome (such as `assertLessEqual(count, 1)` when the effect never fires), an expected `ValidationError` that another rule raises first, a check that only proves a row exists.
2. **Tests that assert a bug.** Expectations read back from the implementation instead of the promise, so they lock the current behavior in, bugs included. Compare each expectation with the method's docstring, name, and callers.
3. **Behavior nobody tests.** Rules with no test, bypass paths (`QuerySet.delete()`, bulk writes, partial saves through `update_fields`), the allowed side of a conditional constraint, and rows a queryset must leave out.
4. **Weak tests.** Input that does not exercise the rule (already-uppercase text for an uppercasing save), unpinned `ValidationError` or `assertRaises(Exception)`, in-memory values instead of stored ones, validation tested through `objects.create()`, an expected `IntegrityError` outside `transaction.atomic()`.
5. **Waste.** Tests of Django itself, or of behavior already proven at the serializer or view layer: they cost run time and prove nothing new.

Confirm a suspicion when it is cheap, with a throwaway probe test that shows the weak test passing on broken behavior, and delete the probe afterwards, so the review leaves nothing changed.

When a test turns out to assert a bug, the model bug is a finding too.

## Report

For each finding give the test (file:line), what it would let through, how you confirmed it, and the concrete fix. List bugs in the model separately from problems with the tests. Change the tests only if the user asked for changes; then follow SKILL.md for writing them.
