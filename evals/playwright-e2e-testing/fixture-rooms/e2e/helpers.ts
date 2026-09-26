import type { Page, Route } from '@playwright/test'

export type Role = 'member' | 'admin' | 'guest'

/** One API request as the app sent it; `path` is relative to /api, `body` is the parsed JSON body or null. */
export interface RecordedRequest {
  method: string
  path: string
  query: Record<string, string>
  body: unknown
}

/** Answers a request and returns true, or returns false to leave it to the next handler. */
export type ApiHandler = (route: Route, request: RecordedRequest) => Promise<boolean>

export const users = {
  member: { id: 7, name: 'Mia Member', role: 'member' },
  admin: { id: 1, name: 'Adam Admin', role: 'admin' },
  guest: { id: 9, name: 'Gus Guest', role: 'guest' },
} as const

/** Answers `method path` (query ignored) with `json` and `status`. */
export const reply =
  (method: string, path: string, json: unknown, status = 200): ApiHandler =>
  async (route, request) => {
    if (request.method !== method || request.path !== path) return false
    await route.fulfill({ status, json })
    return true
  }

/** Routes every API call through `handlers`, records it, and answers unhandled calls with 404 so a spec fails loud. */
export const mockApi = async (page: Page, handlers: ApiHandler[]) => {
  const requests: RecordedRequest[] = []
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const request: RecordedRequest = {
      method: route.request().method(),
      path: url.pathname.replace(/^\/api/, ''),
      query: Object.fromEntries(url.searchParams),
      body: route.request().postDataJSON(),
    }
    requests.push(request)
    for (const handler of handlers) {
      if (await handler(route, request)) return
    }
    await route.fulfill({ status: 404, json: { detail: `Unmocked API call: ${request.method} ${request.path}` } })
  })
  return requests
}

/** Signs in as `role` (null: signed out), mocks the API, and opens `path`. Returns the recorded API requests. */
export const openPage = async (
  page: Page,
  path: string,
  { role = 'member', api = [] }: { role?: Role | null; api?: ApiHandler[] } = {},
) => {
  if (role) {
    const session = { token: `token-${role}`, user: users[role] }
    await page.addInitScript((value) => localStorage.setItem('session', value), JSON.stringify(session))
  }
  const requests = await mockApi(page, api)
  await page.goto(path)
  return requests
}
