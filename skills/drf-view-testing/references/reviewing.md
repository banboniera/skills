# Reviewing view tests

Read the views and their bases first, then the tests, and judge the tests against the standard in SKILL.md: would each one fail if the rule it names broke? Passing tests prove nothing by themselves; the review is about what they would miss.

Review in two directions. From the tests: check each test against the standard. From the views: list every rule each endpoint promises (who may use each action, which rows each route reaches, what each write stores and queues, what each list parameter does), including actions inherited from mixins, and find the test that proves each rule. A rule with no test is a finding even when every existing test is sound, and comparing each rule with its code is how you find the view's own bugs.

## What to look for

Rank findings by how likely each is to let a real regression through:

1. **False greens.** Tests that cannot fail for the reason they name: an anonymous test accepting 401 or 403; a filter, scoping, or stats test whose seeded rows all belong in the result; a query count measured on one row or on rows without related data; an `on_commit` side effect asserted without capturing the callbacks; a permission test run only as a role that passes every check; a direct view call used to assert routing (404, 405) it never exercises.
2. **Tests that assert a bug.** Expectations read back from the implementation instead of the promise, so they lock the current behavior in, bugs included, such as a role reaching an action the docstring reserves for another. Compare each expectation with the view's docstring, the project's rules, and what clients rely on.
3. **Behavior nobody tests.** Rows outside the caller's scope on detail routes and custom actions (not just the list); denied roles for each action; inherited actions; each branch of `get_queryset()` and each query parameter; client-sent owner, tenant, or status on create and update; side effects and their absence on failure; disabled methods.
4. **Weak tests.** A status code with nothing about the body or the stored rows, a write checked through the response instead of the database, an error without its key, a list checked for being non-empty instead of for its ids.
5. **Waste.** Tests of DRF itself, or of serializer rules already proven in serializer tests: they cost run time and prove nothing new.

Confirm a suspicion when it is cheap: temporarily break the rule in the view, or add a throwaway probe test, and run the test to see it still pass. Revert or delete the probe afterwards, so the review leaves nothing changed.

When a test turns out to assert a bug, the view bug is a finding too.

## Report

For each finding give the test (file:line), or for an untested rule the view code (file:line), what it would let through, how you confirmed it, and the concrete fix. List bugs in the views separately from problems with the tests. Change the tests only if the user asked for changes; then follow SKILL.md for writing them.
