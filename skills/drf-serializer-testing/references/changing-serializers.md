# Changing a serializer, and serializer tests that start failing

When a task changes what a serializer accepts, stores, or returns, its tests are the written contract, and they change with it. The risk runs both ways: a test changed to match the new code can hide a regression, and a test left asserting the old behavior blocks an intended change. A serializer also has clients (frontends, mobile apps, other services) that never run your tests, so a change to its input or output is a change to their contract too.

## Before the change

Run the serializer's existing tests and keep the result, so failures that were already there are not blamed on your change. Find everything that depends on the behavior you are about to change: tests that assert it (search for the field, method, and error-code names, including in payload dicts and expected key sets), views that use the serializer, serializers that nest it or inherit from it, and the project's API schema checks, such as a committed OpenAPI file or a schema test. Those tests are the old spec, and the change must update them on purpose rather than discover them by accident.

## Test first

For new or changed behavior, write the test from the new promise before touching the serializer, and run it to see it fail for the right reason: the assertion about the behavior, not an import error, a broken fixture, or an invalid payload failing on another field. Then change the serializer and see it pass. A test written after the code tends to restate the code; one written first states what was asked for. Apply the same standard as for any serializer test: one broken thing per payload, both sides of every boundary, create, full update, and partial update.

## Changes that break clients

Say in your report which clients a change can break, even when the task asked for it:

- **Breaking:** renaming, removing, or retyping an output key (a number that becomes a string, an id that becomes an object); a key that becomes absent instead of null, or null instead of absent; a new required input; a narrower rule rejecting input that used to pass; a new or renamed error key or code that clients branch on; a changed `many=True` error shape.
- **Usually safe:** a new optional input, and a new output key, unless a client validates strictly.

An exact key-set assertion is what catches an unintended contract change, so a changed key set in a test is a contract change to report, never a test detail to update quietly.

## DRF traps when changing a serializer

- **Renaming a field orphans its validator.** DRF finds `validate_<field>()` by the field's name, so after renaming `estimate_hours` to `estimate` (with `source="estimate_hours"` to keep the model field), `validate_estimate_hours()` silently stops running. Rename the method with the field, and keep the tests for its rule: they fail if the rule is lost.
- **Declaring a field that the model used to generate drops what DRF derived for it**: `max_length`, `choices`, `max_digits`, model validators, `allow_null`, `allow_blank`, and `required=False` from a model default. DRF also ignores `extra_kwargs` and `read_only_fields` entries for declared fields. Restate what the field needs, and keep the tests that pin each of those options.
- **Required and defaults behave differently per write.** A new `default` applies on create and full update, never on partial update; `required=False` without a default leaves the key out of `validated_data`. Test the new field through all three writes.
- **Making a field read-only, or excluding it, drops the unique validators it was part of**, and conflicts reach the database as `IntegrityError`. Keep or add a test that expects a validation error for the duplicate.
- **Narrowing a related field's queryset** needs the in-scope and out-of-scope tests on create and on update, and for every serializer that nests this one.
- **Changing `to_representation()` or a nested serializer** changes the output of every serializer that nests it: run those serializers' tests too.

## When existing tests fail after the change

Sort every failure into one of three kinds before editing anything:

- **The old spec.** The test asserts exactly the behavior the task changes. Update it to the new promise in the same change, keeping everything it covered: after a rename, the same boundaries and error codes under the new key. Never delete it or loosen it to "is not valid".
- **A regression.** The test asserts something the task did not ask to change. The change broke it: fix the code, not the test.
- **A test of implementation details.** The test pinned an internal call, an intermediate value, or a query count measured without prefetching rather than a promise. Rewrite it to assert the promise, instead of re-pinning the new details.

Change a test's expectation only when you can tie it to the requested change. List every test whose expectation changed and why: reviewers read that list as the change to the contract.

## When a serializer test starts failing and you did not just change the serializer

Find what changed before deciding anything: read the failure, then `git log -p` on the serializer, the serializers it nests or inherits from, its model and migrations, the settings it reads, and dependency versions, since the test last passed. Then sort the failure into the same three kinds. An intended change updates the test and cites the commit; a regression is reported with the commit that caused it, and fixed only if the user asked for a fix; a test of implementation details is rewritten to its promise.

A DRF or Django upgrade can change behavior clients see. Read the release notes between the two versions, and decide for each failing test whether the new behavior reaches clients. Recent examples: DRF 3.18 returns `many=True` errors as a dict keyed by the index of each invalid item instead of a list (`LIST_SERIALIZER_ERRORS_AS_DICT = False` restores the list, deprecated); DRF 3.17 uses a multi-field `UniqueConstraint`'s `violation_error_code` and message; DRF 3.16 honors a `UniqueConstraint`'s `condition`; DRF 3.15 added validators for `UniqueConstraint`. When clients see the difference, report it as a contract change alongside the updated test.

A test that fails only sometimes has a cause worth finding rather than a retry: state shared between tests outside `setUpTestData`, an unpinned clock, output compared in an order the queryset never promised because it has no `order_by()`, or ids hard-coded in payloads.

## Report

List the tests you added and confirm each failed before the change, the tests whose expectations changed with the reason for each, the client-visible contract changes, any regressions found, and the checks before and after.
