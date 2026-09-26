# Reviewing serializer tests

Read the serializers and their callers first, then the tests, and judge the tests against the standard in SKILL.md: would each one fail if the rule it names broke? Passing tests prove nothing by themselves; the review is about what they would miss.

Review in two directions. From the tests: check each test against the standard. From the serializers: list every rule each one promises (its docstring, fields and their options, related-field querysets, validators, save logic including nested data, and output), and find the test that proves each rule. A rule with no test is a finding even when every existing test is sound, and comparing each rule with its code is how you find the serializer's own bugs.

## What to look for

Rank findings by how likely each is to let a real regression through:

1. **False greens.** Tests that cannot fail for the reason they name: `assertFalse(serializer.is_valid())` on a payload that is also invalid in another way (a missing required field means `validate()` never even runs); `assertRaises(Exception)` around `save()`, which catches DRF's own `AssertionError` for saving invalid data; a query count pinned on an unprefetched queryset, which passes as long as the N+1 stays; output checked with `assertIn` on a few keys.
2. **Tests that assert a bug.** Expectations read back from the implementation instead of the promise, so they lock the current behavior in, bugs included. Compare each expectation with the serializer's docstring, field names, and what clients rely on.
3. **Behavior nobody tests.** Out-of-scope ids on update and inside nested serializers; partial updates, especially of rules that combine fields and of nested data left out of the payload; updates that keep a unique value; the exact output key set and write-only fields; boundaries of configured limits; computed output values; `save(**kwargs)` from the view; fields a client must not set, such as the owner or tenant.
4. **Weak tests.** Input that does not exercise the rule (already-uppercase text for an uppercasing validator, a value that needs no rounding for a rounding rule), an error key without its code, the returned instance or `validated_data` instead of stored rows, create tested but not update.
5. **Waste.** Tests of DRF itself (a plain field rejecting the wrong type), or of behavior already proven at the model or view layer: they cost run time and prove nothing new.

Confirm a suspicion when it is cheap: temporarily break the rule in the serializer, or add a throwaway probe test, and run the test to see it still pass. Revert or delete the probe afterwards, so the review leaves nothing changed.

When a test turns out to assert a bug, the serializer bug is a finding too.

## Report

For each finding give the test (file:line), or for an untested rule the serializer code (file:line), what it would let through, how you confirmed it, and the concrete fix. List bugs in the serializers separately from problems with the tests. Change the tests only if the user asked for changes; then follow SKILL.md for writing them.
