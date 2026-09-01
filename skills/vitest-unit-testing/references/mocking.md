# Mocking mechanics (Vitest 4)

## vi.mock hoisting

`vi.mock('path', factory)` hoisted above all imports — run before module under test load, regardless where written. Consequences:

- Factory **cannot** reference ordinary outer variables (not exist yet). `ReferenceError: Cannot access X before initialization` — move value into `vi.hoisted`:

```ts
const messageSuccess = vi.hoisted(() => vi.fn())
const mockState = vi.hoisted(() => ({ current: { user: fakeUser } }))

vi.mock('antd', async () => {
	const actual = await vi.importActual<typeof import('antd')>('antd')
	return { ...actual, App: { useApp: () => ({ message: { success: messageSuccess } }) } }
})
```

- **No imports inside `vi.hoisted`** — static imports throw there too. Build values from literals and `vi.fn()`.
- Mutable `{ current: ... }` ref from `vi.hoisted` let each test vary mock state by assignment instead of re-mocking.
- Mocking module with default export: factory must return `default` key.
- Aliased paths (`@/store/api`) work in string form. Typed `vi.mock(import('./module'), factory)` overload give inference and refactor-safe paths but **not** resolve TS path aliases — use relative paths with it.

## Ordering: patch globals before module evaluation

Module-level side effects (RTK Query `fetchBaseQuery` capturing `fetch`, code reading storage at import time) see globals **as they were at import**. Patch first, then dynamic import:

```ts
Object.defineProperty(globalThis, 'fetch', { configurable: true, value: fetchMock })
// Dynamic: fetch must be patched before the api module and its injections evaluate.
const { rootApi } = await import('./api')
await import('./app/api') // endpoint injections
```

Top-level `await import(...)` in test file = idiom. Restore originals in `afterAll` same `Object.defineProperty` way.

Same rule for mocks whose factory must win before transitive import: `vi.mock` + `await import('./AppSlice')` at describe level. `vi.doMock` = non-hoisted variant — affect only *subsequent* dynamic imports; use when different tests need different factories for same module.

## Partial mocks

Keep real library, replace boundary:

```ts
vi.mock('@umijs/max', () => createUmiMaxMock({ useModel: () => ({ ... }) }))

vi.mock('antd', async () => {
	const actual = await vi.importActual<typeof import('antd')>('antd')
	return { ...actual, Grid: { ...actual.Grid, useBreakpoint: () => ({ md: true }) } }
})
```

Mock heavy composite children (`DrawerForm`, `ModalForm`, tables, react-pdf primitives) as minimal DOM elements rendering children/props — test then assert *your* wiring, not library UI machinery. Never assert internals of component you mocked.

## vi.fn / vi.spyOn / typing

- `vi.fn(impl)` for callbacks you inject; `vi.spyOn(obj, 'method')` to observe/replace existing method — restore with `.mockRestore()` or `afterEach(() => vi.restoreAllMocks())`.
- Vitest 4: `vi.restoreAllMocks` restore **only** manual `vi.spyOn` spies, no longer reset call state. `vi.clearAllMocks` clear history everywhere; `vi.resetAllMocks` also reset implementations — but Vitest reset `vi.fn(impl)` back to `impl`, not empty function (Jest difference).
- Constructor mocks: implementation must be `function`/`class` — arrow throw on `new`.
- `vi.mocked(imported)` = type-level cast for mocked imports (`{ deep: true }` for nested); runtime identity.
- Concurrent tests: never rely on global clear/reset/restore or shared mutable mocks — race with in-flight tests.

## Timers and time

```ts
beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())
```

- Advance inside `act` when timer trigger React state: `act(() => vi.advanceTimersByTime(100))`.
- Promise-chained timers (polling, async intervals): `await vi.advanceTimersByTimeAsync(ms)` / `runAllTimersAsync` — sync variants not flush microtasks.
- `vi.setSystemTime(date)` fix `Date.now`/`new Date()` — therefore `dayjs()` — but **never fire timers**. Use for date-dependent formatting/logic; use advancement for scheduled callbacks. Restore via `vi.useRealTimers()`.
- user-event with fake timers: `userEvent.setup({ advanceTimers: vi.advanceTimersByTime })`. Without it, awaited interactions hang. Removed `delay: null` workaround: don't use.

## Global/environment stubs

- `vi.stubGlobal('fetch', mock)` + `afterEach(() => vi.unstubAllGlobals())` for per-file globals — except when import-time capture force `Object.defineProperty` + dynamic import pattern above.
- happy-dom gaps — stub locally, restore after: `matchMedia` (object with `matches`/`addEventListener`/`removeEventListener`), `BroadcastChannel`, `URL.createObjectURL`/`revokeObjectURL`, `window.open`, canvas/`createImageBitmap`, `XMLHttpRequest`.
- `window.location` overrides: `Object.defineProperty(window, 'location', { configurable: true, value: ... })`, restore in `afterAll`.

## Reset hygiene

`beforeEach(() => vi.clearAllMocks())` in files with module-level `vi.fn`s — call history must not leak between tests. Restore anything replaced (globals, spies, timers, system time) in `afterEach`/`afterAll`; leaked stub fail *different* file mysteriously.
