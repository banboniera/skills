# HuggingCar Frontend Conventions

Stack: Umi Max (`@umijs/max`), React 19, Ant Design + ProComponents, Redux Toolkit + redux-persist, `react-big-calendar`, Bun, Playwright ~1.62. Suite architecture: **fully mocked backend** — no real API in e2e; specs assert visible UI **plus** recorded backend request contract.

## Commands (Bun, port 9000)

```sh
bun run test:e2e                 # playwright test (builds + previews on 127.0.0.1:9000)
bun run test:e2e -- path.spec.ts # touched spec only
bun run test:e2e:ui              # --ui
bun run test:e2e:debug           # --debug
bun run playwright:install       # chromium --with-deps
bun run typecheck                # includes e2e/tsconfig.json — run after writing specs
```

Coverage gaps (smoke drift, smoke-only pages, missing role matrices, cross-role duplication gaps):

```sh
bun run <skill>/scripts/coverage_gaps.ts <frontend-root>   # exit 1 on drift/missing smoke
```

Config: `playwright.config.ts` — baseURL `http://127.0.0.1:9000`, `fullyParallel`, expect timeout 10s, webServer `bun run build && exec max preview --port 9000` (reused locally, fresh in CI), `maxFailures: 1` in CI. No projects/storageState — auth seeded per test.

## Layout

```
e2e/
├── auth/          login, logout, reset-password (only place UI login happens)
├── manager/       feature specs + pages-smoke.spec.ts (route render matrix)
├── mechanic/      role specs
├── customer/      role specs
└── helpers/       REUSE THESE — never rebuild per spec
```

Frontend paths from `RouteNames` (`@/utils`); backend mock paths may stay literal.

## Helper API (e2e/helpers/)

**Opening pages** — one call: seeds auth, installs API mock dispatcher, mocks common lookups/balance, 404s unknown routes loudly, navigates, waits for app shell:

```ts
// manager.ts / mechanic.ts — return recorded requests
const requests = await openManagerPage(page, path, {
  appState?, lookups?: createLookupsState(overrides), mockApi: handler,
})
const requests = await openMechanicPage(page, path, { lookups?, mockApi })
// customer.ts — no request recording (record ad hoc if needed)
await openCustomerPage(page, path, { lookups?, mockApi })
```

**Handlers** — return `true` if handled, `false` lets helper 404 (loud failure):

```ts
const mockOrdersApi = (data: ListResponse<Row>): ManagerApiHandler =>
  async (route, lookups) => {
    if (apiPathname(route.request().url()) === `${RouteNames.Orders}/` &&
        route.request().method() === HttpMethod.GET) {
      await route.fulfill({ json: data })
      return true
    }
    return false
  }
```

**Request assertions** (`api.ts`): `ApiRequestRecord { method, path, postData?, query }`, `requestsByPath(requests, path)`, `requestBody<T>(request)`. Query params preserved as `string[]`.

**Interactions** (`manager.ts`): `selectComboboxOption(combobox, option)`, `submitTableSearch(page, search)`, `confirmPopup(page)`, `expectInitialPaginationRequest(request)`.

**State** (`reduxState.ts`): `seedReduxState(page, state, userType)` writes `persist:root` (localStorage) + `userType` (sessionStorage) via `addInitScript`; typed `testManagerUser` / `testMechanicUser` / `testCustomerUser`; `createLookupsState(overrides)`.

**Smoke** (`pageSmoke.ts`): `prepareManagerPageSmoke(page)` returns `{ consoleErrors, pageErrors, requests, unhandledApiRoutes }` — smoke specs assert all empty. Keep smoke route matrix aligned with `src/pages`.

## Spec shape

```ts
const openOrdersPage = (page: Page, data = orderResponse) =>
  openManagerPage(page, ordersPath, {
    lookups: createLookupsState(lookupOverrides),
    mockApi: mockOrdersApi(data),
  })

test('filters orders by license plate', async ({ page }) => {
  const requests = await openOrdersPage(page)
  const input = page.getByPlaceholder('Enter license plate')
  await input.fill('ABC123')
  await input.press('Enter')

  await expect(page.getByRole('cell', { name: 'Jan Kowalski' })).toBeVisible()
  await expect.poll(() => orderRequests(requests).length).toBeGreaterThan(0)
  expect(orderRequests(requests).at(-1)?.query.license_plate?.[0]).toBe('ABC123')
})
```

- No `beforeEach`/`afterEach`/storageState in this suite — every test opens own page via helper. Follow that.
- Typed response fixtures local to spec; promote to helper only when specs share contract.
- UI login only in `auth/` specs; everywhere else seed via open helpers.
- Test names describe user behavior.

## Cross-role coverage duplication (deliberate)

Shared code reused across roles — API class, page component, helper originating in one role (e.g. customer API class reused by mechanic/manager) — gets its coverage **duplicated in every role's suite that uses it**, not centralized:

- Base role (where code originates) carries full coverage of it.
- Each reusing role duplicates the applicable tests in its own directory (`manager/`, `mechanic/`, `customer/`), against its own pages and open helper.
- Writing spec for role X page built on shared surface: check sibling role directories for existing coverage of that surface, mirror it in role X.
- Never deduplicate these into one shared spec — per-role duplication IS the feature.
- Mechanical check: `scripts/coverage_gaps.ts` flags CROSS-ROLE GAP for any RouteName in >1 smoke matrix lacking feature coverage in a sharing role.

Why: change to shared code then breaks every dependent role's specs immediately — failure list names exactly which roles the change affects. One central spec would go red once and hide the blast radius.

## Ant Design / third-party surfaces

- Ant tables/forms/modals/drawers expose roles — `getByRole('dialog', { name })`, `cell`, `combobox`, `option`. Use them.
- Combobox flow: click, `pressSequentially`, pick `option` by role (or `selectComboboxOption` helper).
- Accepted CSS exceptions (no accessible surface): `.rbc-*` (react-big-calendar), `.ant-skeleton`, `.ant-statistic`. Comment exception. Anything else with accessible surface: no `.ant-*` selectors.
- Icon-only Ant buttons: add `aria-label` in `src/`, then `getByRole`.

## Known suite debts — do not replicate

New specs must not copy these existing warts:

- Positional `.first()`/`.last()`/`.nth()` where `.filter()` can discriminate.
- `.ant-select-item-option-active` and similar dropdown internals — use `getByRole('option')`.
- Date math from machine clock (`atLocalTime`) — use `page.clock.setFixedTime`, derive fixtures from same instant.
- `boundingBox()` + mouse-coordinate drags — `locator.dragTo()` or locator-based interaction where possible; coordinates unavoidable: assert outcome (request/UI), never gesture.
- Ad-hoc URL-string arrays in customer specs — record `ApiRequestRecord`s like manager/mechanic specs do.
