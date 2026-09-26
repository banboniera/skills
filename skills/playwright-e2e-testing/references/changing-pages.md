# Changing a page, and specs that start failing or flaking

When a task changes what a page shows, who gets which control, what a form accepts, or what the page sends to the backend, its specs are the written contract, and they change with it. The risk runs both ways: a spec changed to match the new code can hide a regression, and a spec left asserting the old behavior blocks an intended change.

## Before the change

Run the specs of the page and keep the result, so failures that were already there are not blamed on your change. Find everything that depends on the behavior you are about to change: specs that assert it (search for the route, the labels and button names, the API paths and parameters involved), other pages that share the component or the API call, and helpers or shared mocks that encode the old contract. Those specs are the old promise, and the change must update them on purpose rather than discover them by accident.

## Test first

For new or changed behavior, change the specs before any edit to the page, however small the change looks: write or update each test to the new promise, and run it to see it fail for the right reason: the assertion about the behavior, not a locator that matches nothing because of a typo, an unmocked request, or a timeout on the wrong page. Then change the page and see it pass. A test written after the code tends to restate the code; one written first states what was asked for. Test the boundary on both sides: when a role gains one control, test that it now has it and can use it (the request it sends), and that it still lacks the neighboring ones.

## Traps when changing a page

- **Showing a control is not the same as allowing the action.** When a role gains a button, check the route guard, the API call, and any check the backend makes; when it loses one, check that the URL behind it is closed too.
- **A changed request shape changes every mock that answers it.** Update the shared mock or fixture once, and search for specs that assert the old query or body.
- **Renamed labels and texts break locators across the suite.** Search for the old text; a spec that still passes after a rename may be asserting an absence that is now trivially true.
- **Screenshot and ARIA snapshot baselines change only on purpose.** Run `--update-snapshots` for the specs the change affects, and read each new baseline before keeping it: an update accepts whatever the page shows now, regressions included.
- **A new loading or error path needs its own test** with a held or failing response; the happy path never runs it.

## When existing specs fail after the change

Sort every failure into one of three kinds before editing anything:

- **The old promise.** The test asserts exactly the behavior the task changes. Update it to the new promise in the same change, keeping everything else it covered: when a role gains a control, the test that expected it hidden becomes one that uses it and checks the request, while the controls that stay hidden keep their assertions. Never delete it or loosen it to "page renders".
- **A regression.** The test asserts something the task did not ask to change. The change broke it: fix the page, not the test.
- **A test of implementation details.** The test pinned a CSS class, a DOM structure, an element's position, or an internal request order the page never promised. Rewrite it to assert the promise instead of re-pinning the new details.

Change a test's expectation only when you can tie it to the requested change. List every test whose expectation changed and why: reviewers read that list as the change to the contract.

## When a spec fails and you did not just change the page

Read the failure before anything else: the error names the locator, what it expected, and what it found. Open the trace (`npx playwright show-trace <trace.zip>`, or rerun with `--trace on`) to see the page at each step, its network calls, and its console. Then find what changed since the spec last passed: `git log -p` on the page, its components, the API client, the shared helpers and mocks, the config, and the dependencies. Sort the failure into the same three kinds. An intended change updates the spec and cites the commit; a regression is reported with the commit that caused it, and fixed only if the user asked for a fix; a test of implementation details is rewritten to its promise.

A Playwright upgrade can change behavior: read the release notes between the two versions (browser builds, removed selector engines, changed defaults) and decide for each failing spec whether the app or the test is affected. After a UI library upgrade, a changed accessible role or name is worth reporting: users of assistive technology see it too.

## When a spec flakes

A spec that fails only sometimes has a cause worth finding rather than a retry. Reproduce it first: `--repeat-each=20`, `--workers=1` versus many, and the failing run's trace (`trace: 'on-first-retry'` in CI records it). Retries and a raised timeout hide the cause; `failOnFlakyTests` makes CI report flakes instead of passing them. The usual causes:

| Symptom | Usual cause | Fix |
| --- | --- | --- |
| Passes alone, fails in the full run | State shared between tests: a module-level variable, a shared account, data another test changes | Each test sets up its own state; unique data per test or worker |
| Fails near midnight, in CI, or on another machine | Machine clock or time zone in the page or the test data | Fixed clock before load, instants with offsets, pinned `timezoneId` |
| An assertion passes or fails depending on timing | A check that runs once (`isVisible()`, `count()`, a recorded-request array read immediately), or an assertion satisfied by the previous or loading state | Web-first assertions; `expect.poll` for recorded requests; anchor on the new state first |
| A mock sometimes misses | Route registered after navigation, or a service worker answering first | Register routes before `goto`; `serviceWorkers: 'block'` |
| The wrong element is used after a data change | `.first()` or `.nth()` | Scope or filter by content |
| A click does nothing | The page is not interactive yet (hydration) | Wait for the state the user waits for; the product should disable the control until it works |
| A drag or click lands in the wrong place | Coordinates from `boundingBox()` and the mouse | `locator.dragTo()` or a locator action; assert the outcome, not the gesture |

Prove the fix with `--repeat-each` on the spec, and report the cause, not just the change.

## Report

List the tests you added and confirm each failed before the change, the tests whose expectations changed with the reason for each, any control or page a role gained or lost, any regressions found, and the runs before and after.
