# Changing code that has tests, and tests that start failing

When a task changes what a function returns, what a component shows or calls back with, what a hook returns, or what a store sends, the tests are the written contract, and they change with it. The risk runs both ways: a test changed to match the new code can hide a regression, and a test left asserting the old behavior blocks an intended change.

## Before the change

Run the tests of the unit and keep the result, so failures that were already there are not blamed on your change. Find everything that depends on the behavior you are about to change: tests that assert it (search for the function, component, prop, and text names and the values involved), the unit's callers and their tests, and shared mocks or fixtures that encode the old shape. Those tests are the old promise, and the change must update them on purpose rather than discover them by accident.

## Test first

For new or changed behavior, change the tests before any edit to the code, however small the change looks: write or update each test to the new promise, and run it to see it fail for the right reason, the assertion about the behavior, not an import error, a typo in a query, or a missing mock. Then change the code and see it pass. A test written after the code tends to restate the code; one written first states what was asked for. Test the boundary on both sides: when a rule is relaxed, test that the newly allowed case works and that the cases still refused are refused.

## Traps when changing code

- **A changed type or payload shape changes every mock and fixture that builds it.** Update the shared ones once, and let the type check find the rest.
- **A changed prop, callback, or return value changes every caller.** Search for the callers, update them, and run their tests too.
- **Renamed texts and labels break queries across tests.** Search for the old text; a test that still passes after a rename may be asserting an absence that is now trivially true.
- **Snapshots change only on purpose.** Update them with `-u` for the tests the change affects, and read each new snapshot before keeping it: an update accepts whatever the code does now, regressions included.

## When existing tests fail after the change

Sort every failure into one of three kinds before editing anything:

- **The old promise.** The test asserts exactly the behavior the task changes. Update it to the new promise in the same change, keeping everything else it covered: when a field becomes optional, the test that expected the error becomes one that expects the blank value to be accepted and sent as the new promise says, while the other fields' rules keep their tests. Never delete it or loosen it to "renders" or "was called".
- **A regression.** The test asserts something the task did not ask to change. The change broke it: fix the code, not the test.
- **A test of implementation details.** The test pinned an internal call, a private state value, a DOM structure, or a call order the unit never promised. Rewrite it to assert the promise instead of re-pinning the new details.

Change a test's expectation only when you can tie it to the requested change. List every test whose expectation changed and why: reviewers read that list as the change to the contract.

## When a test fails and you did not just change the code

Read the failure first: the assertion, the diff, and for a query error the DOM Testing Library prints. Then find what changed since the test last passed: `git log -p` on the unit, the modules it imports, the shared mocks and setup file, the Vitest config, and the dependencies. Sort the failure into the same three kinds. An intended change updates the test and cites the commit; a regression is reported with the commit that caused it, and fixed only if the user asked for a fix; a test of implementation details is rewritten to its promise.

An upgrade can change behavior: read the release notes between the two versions and decide for each failing test whether the code or the test is affected. Recent examples: Vitest 5 clears mock call history before every test by default and throws on `vi.mock` inside a function; Vitest 4 fakes `Date` and every other timer API by default and `vi.restoreAllMocks()` restores only spies; React 19's `act` returns a promise to await for async work; jest-dom 7 added `toHaveAccessibleErrorMessage`, which follows `aria-errormessage` and needs `aria-invalid`.

## When a test fails only sometimes

A test that fails only sometimes has a cause worth finding rather than a retry. Reproduce it: run the file alone and in the full suite, with `--sequence.shuffle`, and repeatedly. The usual causes:

| Symptom | Usual cause | Fix |
| --- | --- | --- |
| Passes alone, fails in the suite or in another order | State left behind: a mock implementation, a stubbed global, fake timers, module-level variables, storage, or a render without cleanup | Set mock behavior per test; restore globals and timers in `afterEach`; check the setup file's cleanup |
| Fails near midnight, on another machine, or in CI | The real clock or the machine's time zone | Fake the clock with `vi.setSystemTime`; write dates with offsets; pin `TZ` for the run |
| An assertion sometimes sees the old state | A check that runs once before an async update (`getBy...` right after an unawaited action) | Await the interaction; `findBy...` or `waitFor` for what appears later |
| A test hangs under fake timers | user-event or a promise waiting on a timer nobody advances | `vi.useFakeTimers({ shouldAdvanceTime: true })` with `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`; `advanceTimersByTimeAsync` for promise chains |
| An "act" warning or an unhandled rejection after the test ended | Work the test started but did not await | Await it, or assert its end state before the test finishes |

Prove the fix by running the test repeatedly, and report the cause, not just the change.

## Report

List the tests you added and confirm each failed before the change, the tests whose expectations changed with the reason for each, any caller or contract the change affects, any regressions found, and the runs before and after.
