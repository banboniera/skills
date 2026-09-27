# Changing an endpoint, and view tests that start failing

When a task changes who may use an endpoint, which rows it reaches, which actions it has, or what it answers, its tests are the written contract, and they change with it. The risk runs both ways: a test changed to match the new code can hide a regression, and a test left asserting the old behavior blocks an intended change. Access changes are security changes: widening what a role may do is exactly the kind of change that must not spread past what was asked.

## Before the change

Run the view's existing tests and keep the result, so failures that were already there are not blamed on your change. Find everything that depends on the behavior you are about to change: tests that assert it (search for the action names, URLs, roles, and status codes involved), views that inherit from this one or share its mixins, and the clients that call the endpoint. Those tests are the old spec, and the change must update them on purpose rather than discover them by accident.

## Test first

For new or changed behavior, write the test from the new promise before touching the view, and run it to see it fail for the right reason: the assertion about the behavior, not an import error, a broken fixture, or a 404 from a wrong URL. Then change the view and see it pass. A test written after the code tends to restate the code; one written first states what was asked for. Test the boundary on both sides: when a role gains one action, test that it can now use that action and still cannot use the neighboring ones.

## Traps when changing a view

- **A new action takes the default branch of `get_permissions()`**, whatever that is. Name it in the branch it belongs to, and test every role against it.
- **`@action(permission_classes=[...])` replaces the view's classes.** Adding it to relax one check drops authentication and every other check the view had.
- **Changing `get_queryset()` changes every route**, the detail routes and every action that uses `get_object()` or `get_queryset()` included, not just the list. Rerun the scoping tests for all of them.
- **A change to a shared base or mixin changes every view that inherits it.** Find them all (search for the class name) and run their tests.
- **Changing `get_serializer_class()` or the serializer an action uses** can make fields writable that were not: test that a client-sent owner, tenant, or status is still ignored.
- **A new filter, search, or ordering parameter** needs rows on both sides of it and another tenant's matching row.

## Changes that break clients

Say in your report which clients a change can break, even when the task asked for it: a URL or `url_path` renamed, a method removed, a status code changed (201 to 200, 404 to 403), an error body reshaped, a pagination envelope or parameter name changed, a filter parameter renamed, a role that loses access. Adding an optional parameter or a new action is usually safe.

## When existing tests fail after the change

Sort every failure into one of three kinds before editing anything:

- **The old spec.** The test asserts exactly the behavior the task changes. Update it to the new promise in the same change, keeping everything it covered: when a role gains an action, the test that refused it becomes one that expects success and checks what was stored, while its other refusals stay. Never delete it or loosen it to "not 500".
- **A regression.** The test asserts something the task did not ask to change. The change broke it: fix the code, not the test.
- **A test of implementation details.** The test pinned an internal call, a query count measured without the related data, or an order the endpoint never promised, rather than a promise. Rewrite it to assert the promise, instead of re-pinning the new details.

Change a test's expectation only when you can tie it to the requested change. List every test whose expectation changed and why: reviewers read that list as the change to the contract.

## When a view test starts failing and you did not just change the view

Find what changed before deciding anything: read the failure, then `git log -p` on the view, its bases and mixins, its serializer, the permission classes, the URLconf, the settings (authentication classes, pagination, filter backends), and dependency versions, since the test last passed. Then sort the failure into the same three kinds. An intended change updates the test and cites the commit; a regression is reported with the commit that caused it, and fixed only if the user asked for a fix; a test of implementation details is rewritten to its promise.

A DRF, django-filter, or Django upgrade can change what clients see. Read the release notes between the two versions, and decide for each failing test whether the new behavior reaches clients. Recent DRF examples: 3.18 returns `many=True` validation errors as a dict keyed by the index of each invalid item instead of a list, and rolls back only connections that were used; 3.15 aligned `SearchFilter` with the admin's search. When clients see the difference, report it as a contract change alongside the updated test.

A test that fails only sometimes has a cause worth finding rather than a retry: a list compared in an order the queryset does not guarantee, throttle counters left in the cache by another test, state shared between tests outside `setUpTestData`, or ids hard-coded in URLs.

## Report

List the tests you added and confirm each failed before the change, the tests whose expectations changed with the reason for each, the client-visible contract changes, any access that widened, any regressions found, and the checks before and after.
