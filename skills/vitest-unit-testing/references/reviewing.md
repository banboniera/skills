# Reviewing unit tests

Read the code under test and the project's test setup first, then the tests, and judge the tests against the standard in SKILL.md: would each one fail if the rule it names broke? Passing tests prove nothing by themselves; the review is about what they would miss.

Review in two directions. From the tests: check each test against the standard. From the code: list every rule each unit promises (each branch and boundary of a function, what a component shows and calls back with for each user action and each result of what it awaits, what a hook returns over time and cleans up, each request a store sends and what the caller gets back), and find the test that proves each one. A rule with no test is a finding even when every existing test is sound, and comparing each rule with the code is how you find the code's own bugs.

## What to look for

Rank findings by how likely each is to let a real regression through:

1. **False greens.** Tests that cannot fail for the reason they name: an `expect` inside a `.then`, `.catch`, or callback that may never run; a promise not awaited, so the test ends before its assertion; an absence (`queryBy...`, `not.toHaveBeenCalled()`, an empty list) with no anchor before it; `toHaveBeenCalled()` or `objectContaining` where the promise is the exact value; `toContain` or `toBeTruthy` on a value with a known exact form; a mock that returns the answer the test then asserts, so the unit's own logic never runs; expected values computed with the unit's own logic; test data where values that could be swapped are equal (an id that equals the owner id).
2. **Tests that assert a bug.** Expectations read back from the implementation instead of the promise, so they lock in the current behavior, bugs included. Compare each expectation with the unit's docs, types, and callers.
3. **Rules nobody tests.** The boundary values and the values just past them; invalid input and what it must not trigger; the failure of each awaited call; each branch of conditional rendering; pending states; cleanup on unmount; each request parameter's cases.
4. **Flakiness risks.** Real timers and sleeps; the real clock or time zone deciding the outcome; mock implementations, globals, or timers left for the next test; order-dependent state.
5. **Weak or costly tests.** `fireEvent` where a user interaction is meant; `getByTestId` or `container.querySelector` where a role or label exists; manual `act` around Testing Library calls; snapshots standing in for assertions; tests of React or a library rather than the code; mocks of the unit's own helpers.

Confirm a suspicion when it is cheap: temporarily break the rule in the code (invert a condition, drop a parameter, change a boundary) and run the test to see it still pass. Revert the change afterwards, so the review leaves nothing changed.

When a test turns out to assert a bug, the code bug is a finding too.

## Report

For each finding give the test (file:line), or for an untested rule the code (file:line), what it would let through, how you confirmed it, and the concrete fix. List bugs in the code separately from problems with the tests. Change the tests only if the user asked for changes; then follow SKILL.md for writing them.
