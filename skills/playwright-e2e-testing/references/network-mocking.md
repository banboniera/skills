# Network Mocking & Request Contracts

## When to mock

- **Third parties always** — never e2e-test systems you don't control (payments, analytics, maps).
- **Own backend**: mock in mocked-suite architecture (deterministic, fast, no server needed) — then request contract IS test's backend assertion: verify method/path/query/body precisely, else suite goes green while integration breaks.
- Real-backend suites: mock only controlled nondeterminism (simulated errors, third parties). Keep at least one path exercising real API.

## Route mocks — always before navigation

```ts
await page.route('**/api/v1/customers/**', async (route) => {
  await route.fulfill({ json: customerListResponse })
})
await page.goto('/customers')   // route registered first, or first request escapes
```

Match method + path in handler; one dispatcher per page-open beats N overlapping `page.route` calls:

```ts
type ApiHandler = (route: Route) => Promise<boolean>   // true = handled

const mockCustomersApi = (data: ListResponse): ApiHandler => async (route) => {
  const url = new URL(route.request().url())
  const method = route.request().method()
  if (url.pathname === '/api/v1/customers/' && method === 'GET') {
    await route.fulfill({ json: data })
    return true
  }
  if (url.pathname === '/api/v1/customers/' && method === 'POST') {
    await route.fulfill({ status: 201, json: createdCustomer })
    return true
  }
  return false
}
```

## Unknown routes fail loudly

Mocked suite that silently 200s or passes through unknown requests hides missing coverage. Terminate dispatcher with loud failure, record what escaped:

```ts
await page.route('**/api/**', async (route) => {
  if (await handler(route)) return
  unhandled.push(route.request().url())
  await route.fulfill({ status: 404, json: { detail: 'unmocked route' } })
})
// later: expect(unhandled).toEqual([])
```

## Recording requests — contract side

Record normalized requests at registration; assert after interacting:

```ts
interface ApiRequestRecord {
  method: string
  path: string
  postData?: unknown
  query: Record<string, string[]>
}

const requests: ApiRequestRecord[] = []
await page.route('**/api/**', async (route) => {
  const req = route.request()
  const url = new URL(req.url())
  requests.push({
    method: req.method(),
    path: url.pathname,
    postData: req.postDataJSON(),
    query: groupParams(url.searchParams),   // preserve repeated params as arrays
  })
  // ...then dispatch/fulfill
})
```

**Assert visible UI first, then request contract** — UI proves user outcome; record proves integration:

```ts
await searchInput.fill('ABC123')
await searchInput.press('Enter')

await expect(page.getByRole('cell', { name: 'Jan Kowalski' })).toBeVisible()
await expect.poll(() => byPath(requests, '/api/v1/customers/').length).toBeGreaterThan(0)
const request = byPath(requests, '/api/v1/customers/').at(-1)
expect(request?.method).toBe('GET')
expect(request?.query.vehicles__license_plate?.[0]).toBe('ABC123')
```

Mutations — assert body, not just occurrence:

```ts
await expect.poll(() => requests.some((r) => {
  const body = r.postData as ServiceOrderBody | undefined
  return r.method === 'POST' && body?.mechanics?.length === 2 && body?.service_bay === 11
})).toBe(true)
```

Read-only guards — assert mutation never fired:

```ts
await event.dblclick()
await expect(page).toHaveURL(currentUrl)          // positive signal first
expect(requests.filter(r => r.method === 'PATCH')).toEqual([])
```

`expect.poll` for first request-arrival check (requests land async); direct `expect` fine once UI assertion already fenced interaction.

## Pending / loading states

Hold route to test in-flight UI, then release:

```ts
let release!: () => void
const gate = new Promise<void>((r) => { release = r })
await page.route('**/api/v1/orders/', async (route) => {
  await gate
  await route.fulfill({ status: 201, json: created })
})

await page.getByRole('button', { name: 'Create' }).click()
await expect(page.getByRole('button', { name: 'Create' })).toBeDisabled()
release()
await expect(dialog).toBeHidden()
```

## Error states

```ts
await route.fulfill({ status: 500, json: { detail: 'boom' } })
// then: await expect(page.getByText('Something went wrong')).toBeVisible()
```

Or `route.abort()` for network failure. Every UI with error surface deserves one such test.

## Patching real responses

Mostly-real data, one controlled field:

```ts
await page.route('**/api/v1/settings/', async (route) => {
  const response = await route.fetch()
  const json = await response.json()
  json.feature_flag = true
  await route.fulfill({ response, json })
})
```

## HAR replay

Stable multi-request fixture recorded once: `page.routeFromHAR('fixture.har', { update: false })`. Good for large read-only datasets; regenerate deliberately, never let `update: true` into CI.

## Service workers

Service worker can shadow route mocks — mocks mysteriously miss: block it, `serviceWorkers: 'block'` in context options.
