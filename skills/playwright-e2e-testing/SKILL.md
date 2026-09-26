---
name: playwright-e2e-testing
description: Writes, maintains, and reviews Playwright end-to-end tests across their lifecycle so the tests catch real regressions — covering pages and flows that already exist, changing a page's behavior test-first, deciding what to do when a spec fails or flakes (including after a Playwright or app upgrade), and reviewing existing specs. Covers what a page promises (visible outcome and the requests it sends), locators, web-first assertions and the races they hide, network mocking and request contracts, roles and auth state, forms and validation, loading, empty and error states, fixed clocks and time zones, and isolation. Use whenever a task writes, reviews, updates, or fixes Playwright tests or *.spec.ts files, adds e2e or browser tests, mocks API responses in a browser test, or changes a page, route, or UI flow that has e2e tests, since the tests change with it. Also use for an "add tests" request on code that turns out to be a page or UI flow, and for a failing or flaky Playwright test. Not for unit or component tests.
---

# Testing pages with Playwright

A page promises what a user can see and do at a URL: which data it shows for which query, which controls each role gets, what each form accepts and rejects, what it sends to the backend, and how it behaves while waiting and when the backend fails. An e2e test exists to fail when any of that breaks. A test that clicks through a flow and checks that something rendered proves little: it passes with the wrong rows, the wrong request, or a control the user should not have. Every task below uses the standard in this file; read the reference that matches the task too.

| Task | Read |
| --- | --- |
| Add specs for pages and flows that already exist | this file |
| Change a page's behavior, or a spec starts failing or flaking | this file and [references/changing-pages.md](references/changing-pages.md) |
| Review existing specs | this file and [references/reviewing.md](references/reviewing.md) |

## The standard

A good e2e test states one thing the page promises, sets up the smallest situation where that promise makes a visible difference, and asserts the outcome exactly. Before keeping a test, ask: if someone deleted or inverted the code behind this promise, would this test fail? If not, it is decoration.

That question drives the choices below.

- **Expected values come from the promise, not the code.** The promise is what the page's docs, comments, ticket, API contract, and users say it does. Reading the component and asserting what it renders only proves the code equals itself, and it passes on the bug. When the promise and the code disagree, you have found a bug (see "When a test exposes a bug").
- **Test both sides of every rule.** The role that gets a control and the role that must not; valid and invalid input; the backend succeeding and failing; the row a filter keeps and the row it drops; the date just before a boundary and the date on it.
- **Assert what the user sees and what the backend receives.** The visible outcome (text, rows, URL, enabled state) and, when the backend is mocked, the exact request: method, path, query, and body. A mocked suite that checks only the screen passes when the page sends the wrong request, because the mock answers anyway.
- **Assert what must not happen.** Invalid input and a cancelled dialog send nothing; a denied role has no control and cannot reach the page by URL; a failed save leaves the old data on screen.
- **Every negative assertion needs a positive anchor.** `toBeHidden()`, `not.toBeVisible()`, `toHaveCount(0)`, and an empty list of recorded requests all pass on a page that never rendered or has not finished loading. First assert something that proves the page reached the state in question, then assert the absence.

## Find the promise

Read the page and everything that gives it behavior before writing anything: the route and its guards, the page component and the components it composes, the API client calls it makes (paths, query parameters, bodies), where it reads the user's role, how it formats dates and numbers, and any docs, comments, tickets, or API schemas describing what it should do. Then read how the suite works: `playwright.config.ts` (`baseURL`, `webServer`, `projects`, `use` options such as `timezoneId`, `locale`, `storageState`), the existing helpers and fixtures, two or three neighboring specs, and the project's test command. Look in AGENTS.md or CLAUDE.md and CI config too.

Work out which kind of suite it is. A mocked-backend suite answers the page's API calls with `page.route` and asserts the requests; a real-backend suite seeds data through the API and asserts what comes back. Follow the project's way: reuse its helpers for signing in, mocking, and recording requests rather than hand-rolling a parallel setup, and extend them only when several specs need the same thing.

Test what the page adds, not the browser, the framework, or a third-party widget's internals; leave pure formatting and logic that needs no browser to unit tests.

## Behaviors and their traps

**Locators.** Find elements the way a user or assistive technology does: `getByRole` with the accessible name, then `getByLabel`, `getByPlaceholder`, `getByText`, and `getByTestId` where the project uses test ids; CSS and XPath only for third-party widgets with no accessible surface, with a comment. Locators are strict: an action on a locator matching several elements throws, so narrow it by scoping (`dialog.getByRole(...)`, `row.getByRole(...)`) or filtering (`.filter({ hasText })`, `.filter({ has })`), not with `.first()` or `.nth()`, which pick whatever is in that position today. Use a position only when order is the promise, and then assert the order. A control with no accessible name (an icon-only button) is an accessibility bug: name it in the product rather than reaching for CSS.

**Assertions and races.** Use web-first assertions (`await expect(locator).toHaveText(...)`), which retry until they pass or time out; `expect(await locator.isVisible()).toBe(true)` checks once and races the page. The retry has a trap of its own: an assertion passes the moment the page matches it, including in the middle of a reload. A button that is disabled while loading satisfies `toBeDisabled()` before the new data arrives; the previous page's rows satisfy a count before the new ones replace them. Assert first something only the new state has (the new rows, the new page number, the request having been sent), then the state you care about. Use `expect.poll` for values outside the DOM, such as recorded requests. Never wait with `waitForTimeout` or `networkidle`: wait for what the user waits for.

**Mocked backends.** Register routes before `page.goto`: a route added after navigation misses the requests the page makes while loading, or catches them by luck of timing. Answer unmocked API calls with a loud failure (a 404 recorded and reported), never a pass-through or a blanket 200. Make each mock answer as the backend would: when the test is about a filter, search, or page, the mock must respond to the parameter (rows that match versus rows that do not), or the screen assertion proves only that the mock returned what it always returns. Assert the request itself with exact values (`toEqual` on the recorded query and body), and assert how many were sent where it matters: one save per click, no request on cancel or invalid input. Remember what a route handler sees: `request.postDataJSON()` is `null` without a body, and the last registered matching route runs first.

**Waiting states.** To test loading and saving states, hold the response on a promise you release: assert the in-flight UI (spinner, disabled button), release, then assert the outcome. A test that never holds the response cannot tell whether the loading state exists.

**Errors.** Answer with the status and body the backend really sends (`{ status: 400, json: { field: ["message"] } }`, a 500, or `route.abort()` for a network failure), and assert what the user sees and what stays: the error message, the form still open with the input kept, the old rows still listed, a retry that repeats the same request.

**Roles and auth.** Sign in by seeding state, not through the login form in every test: a setup project saving `storageState` for a real backend, or the session the app reads (cookies, storage via `addInitScript`) for a mocked one. The login flow gets its own specs. For each gated control and page, test the role that has it and the role that must not, including opening the gated URL directly; asserting that a button is missing proves nothing about the route behind it.

**Forms.** For each validation rule, submit a value that breaks it and assert the message and that nothing was sent, and where the rule has a boundary, test both sides of it (a length at the limit and one over, zero and the smallest value above it where the rule says above zero); then a valid submission and its exact body, including values the page transforms (trimmed, uppercased, converted to the API's date or number format). `toHaveAccessibleErrorMessage` finds a message only through `aria-errormessage` on a field marked `aria-invalid="true"`; otherwise assert the message's text in the field's container. Assert what happens after success (dialog closed, list refreshed, confirmation shown) and after a rejected save (server field errors shown, dialog kept open, the button enabled again).

**Lists, search, and paging.** Seed rows on both sides of each filter and search, and assert the ids or names in the promised order and the request parameters. On a paged list, test what changing a filter does to the page number and that paging keeps the filters: these are separate code paths. Assert the empty state with a positive anchor.

**Time.** Anything that depends on the date (overdue, "today", relative times, calendars, expiry) needs a fixed clock set before the page loads: `await page.clock.setFixedTime(...)`, or `page.clock.install()` when the test also drives timers (then before any other clock call). A time written without an offset (`new Date('2026-04-10T12:00:00')`) is read in the time zone of the test runner, while the page shows it in the browser's `timezoneId` (by default the machine's): write instants with an explicit offset, and pin `timezoneId` where the page's output depends on it, to a zone away from UTC: in UTC the local and the UTC reading of a time are the same, so every mix-up between them passes. Derive the test data from the same fixed instant, put rows on both sides of each boundary (yesterday, today, tomorrow), and try two times of day: one where the local and the UTC date differ (just after local midnight in a zone east of UTC), which catches a page taking today from the UTC date, and midday, which catches a date read as UTC midnight and compared with the current time.

**Navigation.** After a click that navigates, assert the exact URL with `toHaveURL` and something only the destination shows.

**Isolation.** Each test sets up its own state and opens its own page; nothing depends on another test having run or on the order of tests, and `fullyParallel` stays safe. Against a real backend, create unique data per test (or per worker) and do not let tests share accounts that they change.

## Writing the tests

```ts
import { expect, test, type Page } from '@playwright/test'

import { openPage, type ApiHandler, type RecordedRequest } from './helpers' // the project's own: seeds the session, routes the API, records requests, fails unmocked calls

test.use({ timezoneId: 'Europe/Warsaw' }) // the page shows local dates; UTC would hide a UTC/local mix-up

const invoice = (id: number, number: string, due: string) => ({ id, number, due_date: due, status: 'open' })

// The mock answers by query, so a test of the search sees rows appear and disappear.
const invoicesApi: ApiHandler = async (route, request) => {
  if (request.method !== 'GET' || request.path !== '/invoices/') return false
  const all = [invoice(1, 'A-1', '2026-04-09'), invoice(2, 'A-2', '2026-04-10')]
  const results = request.query.number ? all.filter((i) => i.number === request.query.number) : all
  await route.fulfill({ json: { count: results.length, results } })
  return true
}

const sent = (requests: RecordedRequest[], method: string) => requests.filter((r) => r.method === method)
const rows = (page: Page) => page.getByRole('row').filter({ has: page.getByRole('cell') })

test('searching by number shows only the matching invoice', async ({ page }) => {
  const requests = await openPage(page, '/invoices', { role: 'clerk', api: [invoicesApi] })
  await expect(rows(page)).toHaveCount(2)

  await page.getByRole('searchbox', { name: 'Invoice number' }).fill(' a-1 ')
  await page.getByRole('searchbox', { name: 'Invoice number' }).press('Enter')

  await expect(rows(page)).toHaveCount(1)
  await expect(rows(page)).toContainText('A-1')
  expect(sent(requests, 'GET').at(-1)?.query).toEqual({ number: 'A-1', page: '1' })
})

test('overdue marks open invoices due before today, not those due today', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-04-10T12:00:00+02:00'))
  await openPage(page, '/invoices', { role: 'clerk', api: [invoicesApi] })

  await expect(rows(page)).toHaveCount(2)
  await expect(rows(page).filter({ hasText: 'A-1' })).toContainText('Overdue')
  await expect(rows(page).filter({ hasText: 'A-2' })).not.toContainText('Overdue')
})

test('clerks cannot void invoices, from the list or by URL', async ({ page }) => {
  await openPage(page, '/invoices', { role: 'clerk', api: [invoicesApi] })
  await expect(rows(page)).toHaveCount(2) // the anchor: the list has rendered
  await expect(page.getByRole('button', { name: /^Void/ })).toHaveCount(0)

  await page.goto('/invoices/1/void')
  await expect(page.getByRole('heading', { name: 'Not allowed' })).toBeVisible()
})

test('an invalid amount shows an error and sends nothing', async ({ page }) => {
  const requests = await openPage(page, '/invoices/new', { role: 'accountant', api: [invoicesApi] })

  await page.getByLabel('Amount').fill('-5')
  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByLabel('Amount')).toHaveAccessibleErrorMessage('Enter an amount above zero')
  expect(sent(requests, 'POST')).toEqual([])
})
```

- Name each test after the promise it checks, so a failure reads as the broken behavior. Group by feature with `test.describe`; keep the setup in the test or a small local function unless several specs share it.
- Keep typed response fixtures close to the spec, shaped like the real API's responses (reuse the API's types where the project has them), so a mock drifting from the backend fails the type check rather than passing silently.
- A test may check the screen and the request of the same action; one clear flow per test beats one test per assertion.

## When a test exposes a bug

If a test written from the promise fails because the page breaks it, keep the test as written and failing, leave the page unchanged, and finish the rest. Never add a test that asserts behavior you believe is wrong, such as a role seeing a control it should not have. In your report, name the failing test, what the user does, and what the promise says, so the user can decide whether to fix the page. This applies to bugs you find; a change the user asked for follows [references/changing-pages.md](references/changing-pages.md).

## Finish

Run the specs you touched with the project's test command, limited to those files. They pass, except tests you kept because they expose a bug. Run new or changed specs a few times (`--repeat-each=3`) to show they are stable, and run the project's type check if it covers the specs.

Report what you tested, the bugs found with their failing tests, and anything the tests cannot prove, such as behavior that depends on the real backend when the suite mocks it.
