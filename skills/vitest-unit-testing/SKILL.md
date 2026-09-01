---
name: vitest-unit-testing
description: Write and fix Vitest unit/component tests — React Testing Library rendering, user-event interactions, renderHook, vi.mock/vi.hoisted module mocking, fake timers, Redux slice/RTK Query endpoint tests, antd component testing. Use whenever the user asks to unit test, cover, or verify a component, hook, utility, reducer, store endpoint, or page, write or review a *.test.ts / *.test.tsx file, fix a failing or flaky Vitest test, or mock a module/timer/fetch in tests — even if they just say "add tests" for code that turns out to run under Vitest (happy-dom), not in a real browser. Not for Playwright e2e specs under e2e/ (use playwright-e2e-testing).
---

# Vitest Unit Testing

Test **observable contract** — what function return, what user see and trigger in DOM, what request endpoint emit, what state reducer produce. Never component internals, hook implementation order, DOM shape beyond semantics, third-party behavior (antd, dayjs, React): trust library, test only what your code add.

**User naming one behavior never shrink contract.** "Test formatter" still mean: value matrix, boundaries, failure input. Quick verify list = gate, not suggestion.

## Workflow

1. **Inspect project first**: `vitest.config.ts` (environment, setupFiles, aliases), setup file (what already global — matchers, cleanup, storage stubs), shared test helpers, 2–3 neighboring `*.test.*` files. Extend local patterns; never add parallel convention (no new render wrappers, no MSW, no snapshot suites if project has none). HuggingCar frontend: read [references/huggingcar.md](references/huggingcar.md) before writing anything.
2. **Classify unit** — pure function, reducer/slice, RTK Query endpoint/middleware, component, hook, page — pick coverage from table below.
3. **Plan mocks at boundary only**: network, module side effects (Sentry/analytics), heavy third-party children, time. Mock mechanics (hoisting, `vi.hoisted`, partial mocks, fake timers): [references/mocking.md](references/mocking.md). Never mock unit under test or framework hooks wiring it.
4. **Write tests**: one behavior per `it`, behavior-named, colocated (`Foo.test.tsx` beside `Foo.tsx`). Semantic queries, awaited `user-event`, exact assertions.
5. **Run touched file only** (`vitest run path/to/file.test.ts` via project package manager), not whole suite. Failure: read error, fix cause — never widen timeout or wrap in `act` to silence.

## What to cover

| Unit | Do |
|------|-----|
| **Pure function** | Exact outputs across input matrix — `it.each` for value tables. Boundaries (empty, zero, negative, max), malformed input code guards against. Locale/format functions: exact strings, not `toContain`. |
| **Reducer / slice** | `reducer(undefined, action)` for initial state; each action/matcher: given state + action, exact new state. RTK matchers against API actions: synthesize fulfilled/rejected action (`type`, `payload`, `meta.arg`), assert state effect. Side effects in reducers (Sentry, analytics): hoisted spies + assert calls. |
| **RTK endpoint** | Dispatch `endpoint.initiate(arg)` on real `configureStore` + api middleware with `fetch` replaced; assert **emitted request contract**: method, path, query, body. Error paths: non-2xx `Response`, assert `unwrap()` rejection or error handling effect. |
| **Middleware** | Fake `MiddlewareAPI` (`dispatch`, `getState`, `next` as `vi.fn`); assert pass-through for irrelevant actions, effect (dispatch, redirect) for matching. |
| **Component** | Render with boundary mocks; assert what user see (`getByRole`/`getByLabelText` + jest-dom). Every interaction component own: `await user.click/type/...`, then visible outcome or captured callback/mutation payload. Conditional rendering: both branches — `queryBy*` for absence. |
| **Form component** | Initial values shown; user edit, submit, assert **exact mutation/callback payload** (`waitFor`); validation: invalid input shows error + no submission. |
| **Hook** | `renderHook`, assert `result.current` contract; state changes inside `act`; timer hooks: fake timers, advance inside `act`; `rerender` for prop-change behavior, `unmount` for cleanup (no calls after unmount). |
| **Page** | Orchestration: mock data hooks/API/heavy children, assert wiring — right data rendered, user action gives right mutation args, success gives right notification/navigation. Don't re-test mocked children. |

**Skip:** trivial delegation, constant re-exports, third-party behavior, styling, anything covered at better layer (e2e own route-level flows).

## Core patterns

**Component — `userEvent.setup()` per test scope, semantic queries, awaited async:**

```tsx
const user = userEvent.setup()

it('updates the profile email', async () => {
	render(<ProfilePage />)

	const email = screen.getByLabelText(Locales.Input.email.label)
	expect(email).toHaveValue('ada@example.com')

	await user.clear(email)
	await user.type(email, 'new@example.com')
	await user.click(screen.getByRole('button', { name: Locales.Button.save }))

	await waitFor(() =>
		expect(patchCustomer).toHaveBeenCalledWith(
			expect.objectContaining({ email: 'new@example.com' }),
		),
	)
})
```

Appearance: `await screen.findByText(...)` — never `waitFor(() => getBy...)`. Absence: `queryBy*` + `not.toBeInTheDocument()`. Never wrap `render` or user-event in manual `act` — RTL already do; act warning mean update not awaited, not that it need silencing.

**Module mock with mutable state — `vi.hoisted` for anything hoisted factory close over:**

```tsx
const patchCustomer = vi.hoisted(() => vi.fn())
const mockState = vi.hoisted(() => ({ current: { app: { user: fakeUser } } }))

vi.mock('@/store/api', () => ({ usePatchCustomerMutation: () => [patchCustomer] }))
vi.mock('@/hooks/redux', () => ({
	useAppSelector: (selector: (s: typeof mockState.current) => unknown) =>
		selector(mockState.current),
}))
```

Tests vary state by assigning `mockState.current` — no re-mocking per test. Partial mock keep real library except boundary:

```tsx
vi.mock('antd', async () => {
	const actual = await vi.importActual<typeof import('antd')>('antd')
	return { ...actual, App: { useApp: () => ({ message: { success: messageSuccess } }) } }
})
```

**Hook with timers — advance inside `act`, always restore:**

```tsx
beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

it('delays calls until the trailing edge', () => {
	const callback = vi.fn()
	const { result } = renderHook(() => useDebouncedCallback(callback, 100))

	result.current('first')
	act(() => vi.advanceTimersByTime(99))
	expect(callback).not.toHaveBeenCalled()

	act(() => vi.advanceTimersByTime(1))
	expect(callback).toHaveBeenCalledExactlyOnceWith('first')
})
```

Fake timers + user-event: `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`. Date-dependent code: `vi.setSystemTime(...)` (control `dayjs()` too) — never fire timers; advancing do.

**RTK endpoint — patch globals before api module load, assert request:**

```ts
Object.defineProperty(globalThis, 'fetch', { configurable: true, value: fetchMock })
// Dynamic: fetch must be patched before the api module evaluates.
const { rootApi } = await import('./api')

const store = configureStore({
	middleware: (gDM) => gDM().concat(rootApi.middleware),
	reducer: { [rootApi.reducerPath]: rootApi.reducer },
})
await store.dispatch(api.endpoints.deleteVehicle.initiate(3)).unwrap()
expect(requests[0]).toMatchObject({ method: 'DELETE', url: expect.stringContaining('/vehicles/3/') })
```

Fetch mock record `new Request(input, init)` (method, URL, cloned body text), return `Response` — recorded array IS contract assertion surface.

## Anti-patterns

- `fireEvent` where `user-event` model interaction — fire one event, not real sequence (pointer, focus, keyboard); reserve `fireEvent` for low-level cases user-event can't express (raw `blur`, antd select helper).
- `getByTestId`/`container.querySelector` where role/label/text query exist — test nothing accessible, break on restyle.
- `toBeTruthy()`/`toBeNull()` on queries — use jest-dom: `toBeInTheDocument`, `toHaveValue`, `toBeDisabled`, `toBeVisible`; failures then explain themselves.
- Manual `act` around `render`/user-event, or silencing act warnings — warning mean unawaited update; `await` interaction or use `findBy*`.
- `waitFor(() => expect(getBy...))` for appearance — `findBy*` IS retrying query. `waitFor` bodies: assertions only, no side effects, ideally one.
- Mocking react-redux hooks/selectors *when real store cheap* — slices and endpoints use real `configureStore`; hook-level selector mocks for component wiring tests only.
- Snapshot tests for component DOM — encode intent with explicit assertions; snapshots get blindly regenerated.
- Re-mocking module per test instead of one `vi.hoisted` mutable ref.
- Asserting mock plumbing ("my mock was called") when mock not boundary contract — assert visible outcome or payload crossing boundary.
- Copy-pasting same module mock/harness across files — shared boundary: shared helper; one-off: keep local.
- Testing loading spinners/internals of mocked children — mock render them; you test own mock.

## Version notes (Vitest 4)

- `vi.restoreAllMocks` restore **only** manual `vi.spyOn` spies, no longer reset state; `.mockRestore()` still do both. Config `clearMocks`/`mockReset`/`restoreMocks` default false.
- Vitest `mockReset` restore `vi.fn(impl)` to **original** impl (unlike Jest empty fn).
- Constructor mocks: implementation must be `function`/`class` — arrow throw on `new`.
- `workspace` config replaced by `projects`; coverage report only covered files unless `coverage.include` set.
- `vi.mock` factories can't reference outer variables (hoisted above imports) — `vi.hoisted` for values, no imports inside `vi.hoisted`. Full mechanics: [references/mocking.md](references/mocking.md).
- happy-dom faster than jsdom but lack some APIs (matchMedia, BroadcastChannel, canvas, `URL.createObjectURL`) — stub locally per test file, restore after.
- user-event v14: `userEvent.setup()` before render, `await` every interaction; with fake timers pass `advanceTimers`, never `delay: null`.

## Bundled resources

- [references/mocking.md](references/mocking.md) — `vi.mock` hoisting, `vi.hoisted`, dynamic-import ordering, partial mocks, `vi.mocked` typing, spies vs mocks, fake timers/system time, global stubs. Read when any mocking beyond plain `vi.fn` involved.
- [references/huggingcar.md](references/huggingcar.md) — HuggingCar frontend: shared `@/tests` helpers, setup guarantees, antd/umi/pro-components/react-pdf mock recipes, exemplar files, run commands. Read when working in that repo.
- [scripts/untested_files.ts](scripts/untested_files.ts) — list source files with no colocated test. Usage: `bun scripts/untested_files.ts /path/to/frontend/src`.

## Quick verify (gate before finishing)

Every claimed behavior has test named for it. Pure functions: input matrix + boundaries via `it.each`. Components: initial render, each owned interaction, both conditional branches, absence via `queryBy*`. Forms: exact submit payload + validation error path. Hooks: `result.current` contract, timer edges inside `act`, unmount cleanup where relevant. Endpoints/reducers: exact request/state contract, error path. Semantic queries throughout; every user-event awaited; no manual `act` around RTL; no unhandled act warnings in output. Timers/system time restored. Touched test file run and green — test never executed not deliverable.

## References

- https://vitest.dev/api/vi.html
- https://vitest.dev/guide/migration.html
- https://testing-library.com/docs/queries/about/
- https://testing-library.com/docs/user-event/intro/
- https://redux.js.org/usage/writing-tests
- https://kentcdodds.com/blog/common-mistakes-with-react-testing-library
