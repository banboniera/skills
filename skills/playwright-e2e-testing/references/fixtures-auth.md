# Auth, Fixtures, Test Structure

## Two auth strategies — pick by suite architecture

| Suite | Auth strategy |
|-------|---------------|
| **Real backend** | `storageState` via setup project (canonical). Login once, reuse state. |
| **Mocked backend** | Seed client auth state directly (localStorage/sessionStorage/cookies via `addInitScript`) — no server to log into. UI login exercised only in login specs against mocked auth endpoint. |

Either way: **UI login in every test is waste** — slow, injects unrelated failure mode into every spec. Login flow gets own spec; everything else seeds.

## Real backend: storageState + setup project

```ts
// playwright.config.ts
projects: [
  { name: 'setup', testMatch: /.*\.setup\.ts/ },
  {
    name: 'chromium',
    use: { ...devices['Desktop Chrome'], storageState: 'playwright/.auth/user.json' },
    dependencies: ['setup'],
  },
]
```

```ts
// auth.setup.ts
setup('authenticate', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill(process.env.E2E_USER!)
  await page.getByLabel('Password').fill(process.env.E2E_PASSWORD!)
  await page.getByRole('button', { name: 'Login' }).click()
  await expect(page).toHaveURL('/dashboard')          // confirm before saving
  await page.context().storageState({ path: 'playwright/.auth/user.json' })
})
```

- `playwright/.auth/` in `.gitignore` — state files contain impersonating cookies/tokens.
- Shared account only for tests not mutating shared server state. Mutating suites: one account per worker via `testInfo.parallelIndex` in worker-scoped fixture.
- Multiple roles: authenticate each in setup, `role.json` files, `test.use({ storageState: 'playwright/.auth/manager.json' })` per describe/file. Two roles in one test: two browser contexts.
- API login faster than UI login when backend allows: `request.post('/api/login', …)` then `request.storageState({ path })` — interchangeable with browser state.

## Mocked backend: seeded client state

```ts
export async function seedAuthState(page: Page, user: TestUser, role = 'manager') {
  await page.addInitScript(([persisted, r]) => {
    localStorage.setItem('persist:root', persisted)
    sessionStorage.setItem('userType', r)
  }, [serializeState(user), role] as const)
}
```

`addInitScript` runs before app code on every navigation — seed, then `goto`. Pair with role-scoped page-open helper: seeds auth + installs API mock dispatcher + waits for app shell in one call (production example: huggingcar.md). Every spec then starts: `const requests = await openManagerPage(page, path, { mockApi })`.

## Data seeding (real backend)

Playwright `request` fixture exists for preconditions/postconditions:

```ts
test('shows created order', async ({ page, request }) => {
  const order = await request.post('/api/v1/orders/', { data: orderPayload })
  await page.goto('/orders')
  await expect(page.getByRole('cell', { name: orderName })).toBeVisible()
})
```

Seed via API, assert via UI. Create through UI only when creation flow is contract under test. Unique data per test (worker index / random suffix) so `fullyParallel` stays safe; clean up in teardown or disposable environment.

## Fixtures over hooks

Reusable setup with teardown belongs in fixtures — isolated, on-demand, composable:

```ts
export const test = base.extend<{ managerPage: ManagerPage }>({
  managerPage: async ({ page }, use) => {
    await seedAuthState(page, testManager)
    await use(new ManagerPage(page))
  },
})
```

Specs import extended `test` instead of rebuilding infrastructure. `beforeEach` fine for two lines; setup shared across files: fixture.

## POM vs plain helpers — hybrid, not dogma

- **Plain locators/helpers** (default): one-off flows, single-spec interactions. `const searchInput = page.getByPlaceholder(...)` local to spec is complete.
- **Function helpers**: interaction repeated across specs (`selectComboboxOption`, `submitTableSearch`, `confirmPopup`) — small, typed, stateless.
- **POM class**: page with stable, repeated domain vocabulary used by many specs. Inject via fixture, kills constructor boilerplate.

Anti-pattern both directions: god-POM wrapping every locator, hiding assertions; or fifteen specs each re-declaring same five-step form fill. Rule: extract on second duplication, not before.

## Isolation

- Each test gets fresh context/page from Playwright — never share state across tests via module-level mutables.
- No test depends on another's execution or ordering; `fullyParallel: true` must be safe.
- Little setup duplication per test beats hidden coupling.
