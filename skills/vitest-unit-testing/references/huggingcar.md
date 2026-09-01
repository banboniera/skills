# HuggingCar frontend — Vitest specifics

React 19 + @umijs/max + antd 6 + @ant-design/pro-components + RTK 2 (RTK Query) + dayjs + @react-pdf/renderer. Vitest 4, happy-dom, RTL 16, user-event 14, jest-dom. Biome formatting: tabs, single quotes, no semicolons.

## Commands

- Run one file: `bun run test src/path/Foo.test.tsx` (script = `vitest run`; args pass through). Never run whole suite mid-work.
- Typecheck tests: `bun tsc -p tsconfig.vitest.json --noEmit` (strict, `noUncheckedIndexedAccess` — index access need guards).
- Tests colocate beside source: `Foo.test.tsx` next to `Foo.tsx`; pages use `index.test.tsx`. Alias `@` = `src`.

## Already global (src/tests/setup.ts) — never redo in tests

- jest-dom matchers registered.
- RTL `cleanup()` after every test — **no** manual `afterEach(cleanup)`.
- `localStorage`/`sessionStorage` = Map-backed working stubs, cleared after each test — usable directly, no stubbing needed (exception: import-time capture, see endpoint harness below).

No global Provider/router/ConfigProvider wrapper **by design** — components render bare, boundaries mocked per file. No `renderWithProviders`/MSW — competing convention here.

## Shared helpers — `import { ... } from '@/tests'`

| Helper | Use |
|--------|-----|
| `createUmiMaxMock({ formatMessage?, useModel?, useAntdConfigSetter? })` | Factory for `vi.mock('@umijs/max', () => createUmiMaxMock(...))`. Provide `useIntl`/`FormattedMessage` returning message **id** — so `Locales.*` keys = accessible names in queries. |
| `formatMessageWithValues` | Pass as `formatMessage` when component interpolate values: render `` `${id}:${JSON.stringify(values)}` ``, assert on that string. |
| `mockReduxModule(stateRef)` | `{ useAppSelector }` reading mutable `{ current }` state ref — for `vi.mock('@/hooks/redux', ...)`. |
| `mockResolvedTrigger(mock, result)` | Make RTK mutation trigger mock return `{ unwrap: () => Promise.resolve(result) }`. |
| `openAntdSelect(index?)` | `fireEvent.mouseDown` on nth combobox — sanctioned way to open antd Select/AutoComplete popups; then `await screen.findByText(...)` for portal options. |
| `setTestLocation(path)` | `history.pushState` for location-dependent code. |

## Mock recipes (established in repo)

- **@umijs/max**: `vi.mock('@umijs/max', () => createUmiMaxMock())`; add `useModel`/`history`/`useAccess` keys per component need. i18n text assert against `Locales.*` ids.
- **antd**: partial mock via `importActual`, override only boundary — `App.useApp` (notifications), `Grid.useBreakpoint`, `Dropdown`, `Upload.Dragger`, `Image`. Forms: use **real** antd `Form.useForm()`, assert `form.getFieldValue/getFieldError` or visible values — never mock Form.
- **@ant-design/pro-components**: mock composites (`DrawerForm`, `ModalForm`, `ProForm.Group`, `ProFormDependency`, table components) as tiny components rendering children/props. Keep mocks dumb — no reimplementing validation/UI logic inside mock; assert rules/props component pass instead.
- **Redux in components**: mock `@/hooks/redux` with `mockReduxModule`/selector-over-ref; mock API hooks (`useXxxMutation` = `[trigger]` with `mockResolvedTrigger`). Real stores only in slice/endpoint/middleware tests.
- **Side-effect modules**: `@sentry/react` (`captureException`, `setUser`), PostHog utilities mocked with hoisted `vi.fn`s; slices importing them use `vi.mock` + `await import('./AppSlice')`.
- **@react-pdf/renderer**: mock primitives (`Document`, `Page`, `View`, `Text`, `Link`, `StyleSheet.create: (s) => s`) as DOM tags; capture structured props (table rows) into `vi.hoisted` array, assert on it. `useOpenPDF`-style hooks: mock `pdf().toBlob`, `URL.createObjectURL/revokeObjectURL`, `window.open`; real `@cantoo/pdf-lib` may inspect produced bytes.
- **happy-dom gaps**: local stubs per file — `matchMedia` (ThemeToggle), `BroadcastChannel` (session idle), `XMLHttpRequest`/`createImageBitmap`/canvas (ModalFiles). Restore after.

## RTK endpoint test harness (customerEndpoints.test.ts pattern)

`fetchBaseQuery` and auth headers capture `fetch`/`sessionStorage` at import — so: `Object.defineProperty(globalThis, 'fetch', ...)` with recording mock (push `{ method, url, body }` from `new Request(input, init)`, return `Response`), **then** `await import('./api')` + endpoint-injection modules, then `configureStore` with `rootApi.reducer` + `.concat(rootApi.middleware)`. Dispatch with `.unwrap()` so rejected request fail test. Assert recorded requests via `backendPathname` (strip `/api-(customer|manager|mechanic)` prefix) or full pathname when prefix itself = contract. Reset `requests.length = 0` in `beforeEach`; restore originals in `afterAll`.

## Conventions

- `describe('SubjectName')` + `it('does behavior ...')` — no `test()`.
- `it.each([[case, input, expected], ...])('formats %s', ...)` for value matrices (see `financial.test.ts`, `date.test.ts`).
- Queries: `getByRole(name)`/`getByLabelText(Locales...)`/`getByDisplayValue`; `findBy*` for async; `queryBy*` for absence. `userEvent.setup()` + awaited interactions.
- `fireEvent` legitimate only for: `openAntdSelect`, raw `focus`/`blur`/`input` edges user-event can't express.
- dayjs never mocked — date tests extend plugins directly, pass explicit dates; time-sensitive logic use `vi.setSystemTime`.

**No copy from legacy files**: `toBeTruthy()`/`toBeNull()` on queries, `container.querySelector`, redundant manual `cleanup()` — older tests carry these; dominant convention above win.

## Exemplars (best per category)

| Category | File |
|----------|------|
| Pure function matrix | `src/utils/functions/financial.test.ts` |
| RTK cache utils | `src/store/utils/query.test.ts` |
| Slice + side effects | `src/store/reducers/app/AppSlice.test.ts` |
| Endpoint request contract | `src/store/reducers/customerEndpoints.test.ts` |
| Middleware | `src/store/middleware/unauthorizedMiddleware.test.ts` |
| Component (antd/pro mocks) | `src/components/other/table/TableList.test.tsx` |
| Hook + fake timers | `src/hooks/debounce/useDebouncedCallback.test.tsx` |
| PDF document | `src/components/pdf/ServiceOrderPDFDocument.test.tsx` |
| PDF hook | `src/hooks/pdf/useOpenPDF.test.tsx` |
| Page (form + mutation) | `src/pages/profile/index.test.tsx` |
