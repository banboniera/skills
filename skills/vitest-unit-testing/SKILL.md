---
name: vitest-unit-testing
description: Writes, maintains, and reviews Vitest unit and component tests across their lifecycle so the tests catch real regressions — covering code that already exists, changing a function, component, hook, or store test-first, deciding what to do when a test starts failing (including after a Vitest, React, or library upgrade), and reviewing existing tests. Covers pure functions and their boundaries, React components through Testing Library and user-event, hooks, fake timers and dates, module and global mocks, fetch and RTK Query requests, reducers and selectors, async code whose assertions never run, and happy-dom limits. Use whenever a task writes, reviews, updates, or fixes *.test.ts or *.test.tsx files, adds unit or component tests, mocks a module, timer, or fetch in a test, or changes code that has unit tests, since the tests change with it. Also use for an "add tests" request on code that turns out to run under Vitest, and for a failing or flaky Vitest test. Not for Playwright end-to-end specs.
---

# Testing units with Vitest

A unit promises something to its callers: a function returns given values for given inputs and refuses the rest, a component shows what its props and state say and calls back with the right values when the user acts, a hook returns the right value over time and cleans up, a store sends the right requests and holds the right state. A test exists to fail when any of that breaks. Coverage does not show that: a test can run every line and still pass on broken code, because it checks that something rendered or was called, not what.

| Task | Read |
| --- | --- |
| Add tests for code that already exists | this file |
| Change code that has tests, or a test starts failing | this file and [references/changing-code.md](references/changing-code.md) |
| Review existing tests | this file and [references/reviewing.md](references/reviewing.md) |

## The standard

A good test states one rule the unit promises, sets up the smallest case where that rule makes a visible difference, and asserts the outcome exactly. Before keeping a test, ask: if someone deleted or inverted the code behind this rule, would this test fail? If not, it is decoration.

That question drives the choices below.

- **Expected values come from the promise, not the code.** The promise is what the unit's docs, comments, types, callers, and ticket say it does. Reading the implementation and asserting what it returns only proves the code equals itself, and it passes on the bug. Write expected values out literally; never compute them with the same logic the unit uses. When the promise and the code disagree, you have found a bug (see "When a test exposes a bug").
- **Test both sides of every rule.** Each branch, each boundary and the value just past it (zero and one, the limit and one over, one decimal and two), valid and invalid input, success and failure of every call the unit awaits.
- **Assert the exact outcome.** `toBe` and `toEqual` on whole values, `toHaveBeenCalledExactlyOnceWith` on callbacks and requests, the exact text or state a user sees. `toContain`, `toBeTruthy`, `toHaveBeenCalled()` without arguments, and `expect.objectContaining` where the whole value is the promise all pass on wrong results.
- **Make values that could be mixed up differ.** When a call or payload carries several values of one kind (an id and an owner id, a page and a page size, a start and an end), give each a different value in the test; if they are equal, code that sends the wrong one passes.
- **Assert what must not happen.** Invalid input submits nothing; a cancelled action calls nothing; a failed request leaves the old state; a denied branch renders no control.
- **Every assertion must run, and every absence needs an anchor.** Await every promise the test starts. An `expect` inside a `.then`, `.catch`, callback, or event handler may never run, and the test passes; `await expect(promise).rejects...` or `expect.assertions(n)` make it count. A `queryBy...` that finds nothing, `not.toHaveBeenCalled()`, and an empty list also pass before the component has rendered or the async work has finished: first assert something that proves the state was reached.

## Find the promise

Read the unit and everything that gives it behavior before writing anything: its docs and comments, its types, the modules it imports, and how its callers use it (which return values, props, and callbacks they rely on). For a component, read the child components and hooks it uses; for a store, the base query, the endpoints, and their tags.

Then read how the project tests: `vitest.config` (environment, `globals`, `setupFiles`, `clearMocks`, `restoreMocks`, `unstubGlobals`, aliases), the setup file (what is already global, such as jest-dom matchers, Testing Library cleanup, storage stubs), shared test helpers and mocks, and two or three neighboring test files. Look in AGENTS.md or CLAUDE.md too. Follow the project's way: reuse its helpers and mocks, keep its file layout, and do not add a second convention (a new render wrapper, MSW beside hand-written fetch stubs, snapshots in a suite that has none).

Decide what the unit is and where its boundary lies. Mock only what the unit reaches outside itself that a test cannot run or control: the network, time, randomness, browser APIs happy-dom lacks, and heavy third-party UI when the project mocks it. Never mock the unit, its own helpers, or the framework wiring it together; a real store, real child components, and real library code prove more than mocks of them.

Test what the unit adds, not React, the router, the UI library, or the state library: a test that `useState` updates or that a library's component renders proves nothing about your code.

## Behaviors and their traps

**Functions.** List the cases from the promise and put them in a table with `it.each` (or `test.for`), one row per branch and boundary, with literal expected values. Include the inputs the function must refuse and what it returns or throws for them (`expect(() => f(x)).toThrow(...)`, awaited `rejects` for async). For formatted output (money, dates, plurals), assert the whole string.

**Components.** Render the component as its caller does and interact as a user does: `const user = userEvent.setup()` before rendering, `await` every `user.click`, `user.type`, `user.selectOptions`. Find elements by role and accessible name, then label, then text (`getByRole('button', { name: 'Save' })`, `getByLabelText('Amount')`); `getByTestId` and `container.querySelector` test markup rather than what users perceive. Assert what the user sees and what the component calls back with, exactly. Test each branch of conditional rendering, with an anchor before each absence. Use `findBy...` for something that appears later, and keep a `waitFor` callback to the one assertion you are waiting for. Do not wrap `render` or user-event in `act`: they already are. An act warning means an update you did not await, but React prints it only when `IS_REACT_ACT_ENVIRONMENT` is true, which Testing Library sets itself only when Vitest globals are on: without it, a quiet run proves nothing. Use `fireEvent` only for what user-event cannot express.

**Async actions in components.** When a component awaits a callback or request, control its promise: hold it (a promise you resolve later) to assert the pending state (disabled button, "Saving…"), resolve it to assert success, and reject it the way the backend does to assert the error state, the kept input, and the control enabled again.

**Hooks.** Use `renderHook` with `initialProps` and `rerender` to change arguments, `result.current` for the latest value, and `unmount` for cleanup. Wrap calls that update state outside Testing Library in `act`. Test the hook through a small component when its promise is about what a user sees.

**Timers and dates.** `vi.useFakeTimers()` in `beforeEach` and `vi.useRealTimers()` in `afterEach`. Fake timers also fake `Date`; `vi.setSystemTime()` sets the clock without firing timers. Advance with `act(() => vi.advanceTimersByTime(ms))`, or `await act(() => vi.advanceTimersByTimeAsync(ms))` when promises run between timers. Test the boundary: nothing at `delay - 1`, the effect at `delay`, the wait restarting on a new change, nothing left after unmount (`vi.getTimerCount()`). user-event waits on timers and hangs under plain fake timers, even with its `advanceTimers` option: use `vi.useFakeTimers({ shouldAdvanceTime: true })` with `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`. The clock then also moves with real time, so assert exact timer boundaries with `advanceTimersByTime` steps rather than across user-event calls. A date string without an offset (`new Date('2026-04-10T12:00:00')`) is read in the test runner's time zone, and a date-only string (`'2026-04-10'`) as UTC midnight: set the clock in the zone the code works in, and test times of day where local and UTC dates differ (just after midnight, just before).

**Module mocks.** `vi.mock(path, factory)` is hoisted above the imports, so for a statically imported module its factory runs before the file's own variables exist: create what it needs with `vi.hoisted(() => ...)`. Call `vi.mock` only at the top level; inside a test or function it fails the whole file in Vitest 5. Mock the module path the unit imports; keep the rest of a library with `await vi.importActual(...)` and replace only the boundary. `vi.mocked(fn)` types a mocked import. Use `vi.doMock` with a dynamic `import()` when tests need different factories for the same module. Globals: `vi.stubGlobal` with `vi.unstubAllGlobals()` afterwards, or the project's own stubs.

**Mock state between tests.** Vitest 5 clears call history before every test by default (`clearMocks: true`) but keeps implementations: a `mockReturnValue` or `mockImplementation` set in one test leaks into the next unless the project sets `mockReset` or `restoreMocks`, or the test sets it again. `vi.restoreAllMocks()` restores only `vi.spyOn` spies. Set each test's mock behavior in that test or in `beforeEach`.

**Requests.** Replace `fetch` (or use the project's MSW handlers) and record each request: method, path, query, and body, read from the `Request`. Drive the real code (the real API client or RTK Query store with its middleware), then assert the exact requests and what the caller gets back, including the error shape for a failing status. For RTK Query, also test what the tags promise: after a mutation, the affected query is fetched again. RTK Query's `fetchBaseQuery` looks `fetch` up on every request, so stubbing it after the import works; a client that stores `fetch` at import time needs the stub before it is imported.

**Reducers and selectors.** `reducer(undefined, { type: 'init' })` for the initial state; for each action, a state before and the exact state after, including the fields that must not change. Feed selectors state that contains the rows they must leave out.

**happy-dom limits.** No layout (`getBoundingClientRect` returns zeros); CSS files imported by components are not loaded, so `toBeVisible` sees inline styles, `hidden`, and `<style>` elements in the document, not the app's stylesheets; and browser APIs such as `matchMedia`, `ResizeObserver`, and `IntersectionObserver` exist without doing what a browser does. A test that stubs one of these does not exercise the behavior that depends on it; say so in your report, and leave that behavior to an end-to-end test.

**Snapshots.** A snapshot passes whatever it first recorded and is re-recorded without being read. Use one only for stable serialized output nobody would assert field by field, and prefer small inline snapshots; assert behavior with explicit expectations.

## Writing the tests

```tsx
import { act, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { OrderForm } from './OrderForm'
import { parseQuantity } from './quantity'
import { useCountdown } from './useCountdown'

describe('parseQuantity', () => {
  it.each([
    ['1', 1],
    ['  12 ', 12],
    ['999', 999],
  ])('reads %j as %i', (text, expected) => {
    expect(parseQuantity(text)).toBe(expected)
  })

  it.each(['', '0', '1000', '1.5', '-1', 'ten'])('refuses %j', (text) => {
    expect(parseQuantity(text)).toBeNull()
  })
})

describe('OrderForm', () => {
  it('submits the cleaned order once', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    const user = userEvent.setup()
    render(<OrderForm onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText('Quantity'), ' 12 ')
    await user.click(screen.getByRole('button', { name: 'Order' }))

    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ quantity: 12 })
  })

  it('refuses a quantity of zero and submits nothing', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    const user = userEvent.setup()
    render(<OrderForm onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText('Quantity'), '0')
    await user.click(screen.getByRole('button', { name: 'Order' }))

    expect(screen.getByText('Order at least one')).toBeInTheDocument() // the anchor: validation ran
    expect(onSubmit).not.toHaveBeenCalled()
  })
})

describe('useCountdown', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('ticks once a second and stops at zero', () => {
    const { result } = renderHook(() => useCountdown(2))
    act(() => vi.advanceTimersByTime(999))
    expect(result.current).toBe(2)
    act(() => vi.advanceTimersByTime(1))
    expect(result.current).toBe(1)
    act(() => vi.advanceTimersByTime(5000))
    expect(result.current).toBe(0)
    expect(vi.getTimerCount()).toBe(0)
  })
})
```

- Name each test after the rule it checks, so a failure reads as the broken promise. Group with `describe` by unit, and keep setup in the test or a small local function unless several files share it.
- Keep each test independent: its own render, mocks, and data; nothing relies on another test having run.
- Keep fixtures typed with the real types, so a change in the shape the code expects fails the type check.

## When a test exposes a bug

If a test written from the promise fails because the code breaks it, keep the test as written and failing, leave the code unchanged, and finish the rest. Never add a test that asserts behavior you believe is wrong, such as a control staying disabled after an error it should recover from. In your report, name the failing test, the input, and what the promise says, so the user can decide whether to fix the code. This applies to bugs you find; a change the user asked for follows [references/changing-code.md](references/changing-code.md).

## Finish

Run the test files you touched with the project's test command, limited to those files. They pass, except tests you kept because they expose a bug, and the run shows no unhandled errors or act warnings. Run them again with `--sequence.shuffle` to show they do not depend on order, and run the project's type check if it covers tests.

Report what you tested, the bugs found with their failing tests, and anything the tests cannot prove, such as behavior that depends on real layout, a real browser API, or the real backend.
