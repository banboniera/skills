# Reviewing e2e specs

Read the page and the helpers the specs use first, then the specs, and judge the specs against the standard in SKILL.md: would each one fail if the behavior it names broke? Passing specs prove nothing by themselves; the review is about what they would miss.

Review in two directions. From the specs: check each test against the standard. From the page: list every promise it makes (what each role sees and can do, what each filter, search, and page sends and shows, each validation rule, each request and its body, the loading, empty, and error states, what depends on the date), and find the test that proves each one. A promise with no test is a finding even when every existing test is sound, and comparing each promise with the page's code is how you find the page's own bugs.

## What to look for

Rank findings by how likely each is to let a real regression through:

1. **False greens.** Tests that cannot fail for the reason they name: a negative assertion (`toBeHidden`, `not.toBeVisible`, `toHaveCount(0)`, an empty request list) with no positive anchor before it; `expect(await locator.isVisible())` or a count read once; an assertion that the loading or previous state also satisfies; a mock that ignores the parameter under test, so the screen shows the same rows whatever the page sends; a request asserted by its occurrence only, or with `objectContaining` where the promise is the whole body; a route registered after `goto` or matching a path the page never calls, so the test runs against something else; a `test.skip`, `test.fixme`, or a condition (`if (await x.isVisible())`) that skips the assertions.
2. **Tests that assert a bug.** Expectations read back from the component instead of the promise, so they lock in the current behavior, bugs included, such as a role seeing a control the docs reserve for another. Compare each expectation with the page's docs, the ticket, and the API contract.
3. **Promises nobody tests.** The denied role and the gated URL; each validation rule and that nothing is sent; the exact body of each write; filters and paging together; loading, empty, and error states; date boundaries; what happens after a save fails.
4. **Flakiness risks.** Fixed sleeps and `networkidle`; the machine clock or time zone deciding the outcome; `.first()` and `.nth()` where content can discriminate; state shared between tests; routes registered after navigation.
5. **Weak or costly tests.** CSS selectors where an accessible locator exists; assertions on DOM structure or classes; UI login repeated in every test; one test per trivial assertion; tests of the framework or a third-party widget.

Confirm a suspicion when it is cheap: temporarily break the behavior in the page (invert a condition, drop a parameter, change a label) and run the spec to see it still pass. Revert the change afterwards, so the review leaves nothing changed.

When a test turns out to assert a bug, the page bug is a finding too.

## Report

For each finding give the test (file:line), or for an untested promise the page code (file:line), what it would let through, how you confirmed it, and the concrete fix. List bugs in the page separately from problems with the specs. Change the specs only if the user asked for changes; then follow SKILL.md for writing them.
