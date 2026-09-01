---
name: playwright-e2e-testing
description: Write and fix Playwright end-to-end tests — spec authoring, locators, web-first assertions, network mocking, auth state, fixtures, flaky-test debugging, CI config. Use whenever user asks to test, cover, or verify web app behavior in a browser, add e2e or integration tests, write or review a *.spec.ts under e2e/ or tests/, fix a flaky or failing Playwright test, mock API responses, seed auth state, or configure Playwright for CI — even if they just say "add tests" for code that turns out to be a page, route, or UI flow.
---

# Playwright E2E Testing

Test **user-visible route behavior**: what user sees and does at URL, plus — in mocked suites — exact backend request contract (method/path/query/body) UI emits. Never test component internals, DOM shape, styling classes, third-party systems you don't control. E2E test answers: this route, this user, this interaction — this visible outcome, this network contract?

**User naming one behavior never shrinks contract.** "Test the filter" still means: visible result, emitted query params, empty state for that flow. Quick-verify list = gate, not suggestion.

## Workflow

1. **Inspect project first**: `playwright.config.ts` (baseURL, webServer, projects, use), package manager + scripts, existing `e2e/`/`tests/` helpers and 2–3 neighboring specs. Extend local patterns; never introduce parallel framework. HuggingCar frontend: read [references/huggingcar.md](references/huggingcar.md) before writing anything.
2. **Classify suite**: mocked backend (route intercepts, seeded client state) vs real backend (API seeding, storageState auth). Classification decides auth + data strategy — see [references/fixtures-auth.md](references/fixtures-auth.md).
3. **Read exact reference needed** (table below). Don't guess API shapes.
4. **Write specs**: mocks before navigation, accessible locators, one user behavior per test, behavior-named. Assert visible UI first, then request side effects. Cover per "What to cover" table — happy path alone is not a page spec: form/mutation pages need at least the invalid-input case (visible error + no request). Broken validation ships silently otherwise; it's the cheapest high-value second test.
5. **Run touched spec only** (`npx playwright test path/to.spec.ts` or project equivalent), not whole suite. Failure: trace, not guesswork. Before finishing: walk Quick verify list line by line against your spec — each unmet line is a missing test, not optional polish.

## Read path

| Need | Read |
|------|------|
| Locator choice, chaining, web-first assertions, aria snapshots | [references/locators-assertions.md](references/locators-assertions.md) |
| Route mocks, request recording, contract assertions, HAR | [references/network-mocking.md](references/network-mocking.md) |
| Auth (storageState / seeded state), fixtures, POM-vs-helpers | [references/fixtures-auth.md](references/fixtures-auth.md) |
| Failing/flaky test, traces, deterministic time | [references/debugging-flaky.md](references/debugging-flaky.md) |
| Config, workers, sharding, reporters, CI pipeline | [references/ci.md](references/ci.md) |
| HuggingCar frontend specifics (helpers, commands, conventions) | [references/huggingcar.md](references/huggingcar.md) |
| Which pages lack coverage (smoke drift, smoke-only, missing matrices) | run [scripts/coverage_gaps.ts](scripts/coverage_gaps.ts) against frontend root |

## What to cover

| Area | Do |
|------|-----|
| **Render** | Route loads: key landmark visible (heading, table, form) — not "page didn't crash". Smoke suites separately: render + zero console/page errors + zero unmocked requests. |
| **Happy flow** | Primary user journey: fill, submit, visible confirmation. |
| **Request contract** (mocked suites) | Every mutating interaction: assert method/path + exact body/query UI sent. Filters/search/sort/pagination: assert emitted query params. |
| **Role/access gating** | Gated page or control: allowed role sees it, rejected role doesn't (or redirected). Read-only roles: assert mutation request **never** sent. |
| **Validation** | Invalid input: visible error + no request emitted (or rejected request surfaced). |
| **States** | Empty, loading (hold route, assert spinner/disabled, release), error responses UI must survive. |
| **Navigation** | Navigating interactions: `expect(page).toHaveURL()` with specific target. |

## Non-negotiables

- **Locators**: `getByRole` (accessible name) then `getByLabel` then `getByPlaceholder` then `getByText` then `getByTestId`; CSS only for third-party composites with no accessible surface. Ambiguity: `.filter()`/chaining, not `.first()`/`.nth()`. Icon-only control unreachable by role: add `aria-label` in product, don't work around in test.
- **Assertions**: web-first only — `await expect(locator).toBeVisible()`. Never `await locator.isVisible()` into sync `expect` (checks once, no retry). `expect.poll` only for non-DOM state (recorded requests, counters).
- **Waiting**: no `waitForTimeout`, no `networkidle`. Actions auto-wait; navigation: `toHaveURL`; readiness: assert element user needs.
- **Time**: date-dependent UI needs `page.clock.setFixedTime(...)` before load. Machine clock/timezone never decides test outcome.
- **Isolation**: each test seeds own state, opens own page — no cross-test dependencies, no shared mutable accounts. `fullyParallel` must stay safe.
- **Mocks before `goto`**; unknown API routes fail loudly (404/500 + recorded), never silently pass through.
- **Test names** describe user behavior ("filters orders by license plate"), not implementation.

## Anti-patterns

- CSS class/`#id` selectors where accessible locator exists — breaks on restyle, tests nothing user-facing.
- Positional `.first()`/`.last()`/`.nth()` to dodge ambiguity — reorder = false pass/fail; discriminate by content.
- Sleep-and-hope (`waitForTimeout`) or `networkidle` readiness — flake factories; assert product condition.
- Asserting only that request happened — contract is *what* was sent; check body/query.
- Testing third-party widget internals (calendar libs, select dropdown DOM) beyond interaction user performs.
- Copy-pasting mock fixtures/handlers across specs — shared contract: shared helper; local one-off: keep local.
- Retries as fix — test passing on retry = bug with green checkmark; diagnose trace.
- Giant page objects wrapping every locator — POM only for repeated domain flows; direct locators for one-offs.
- Coordinate clicks (`boundingBox` + mouse math) when locator click works — viewport-dependent.
- E2E-testing through UI what API can seed — UI setup only when that UI flow *is* the contract.

## Version notes (Playwright 1.62)

- `page.clock` (`setFixedTime` recommended; `install` before any other clock call) — all date/time-dependent UI.
- `expect(page).toMatchAriaSnapshot()` — YAML accessibility-tree match; stable structure (menus, nav); targeted assertions for behavior.
- `retryStrategy: 'isolated'` — retries deferred, run isolated; retries still need diagnosis.
- Component testing = stable stories/gallery model (replaces `@playwright/experimental-ct-*`) — regular test against app-owned gallery page.
- `storageState` may carry credentials/passkeys — auth state files stay gitignored.
- `expect(locator).toHaveAccessibleErrorMessage()` — asserts `aria-errormessage`; natural fit for validation tests.
- `--last-failed` — rerun only previous failures. Drags: `locator.dragTo(target)` for element drags (never mouse-coordinate math); `locator.drop(payload)` (1.60+) synthesizes file/data drops onto dropzones.
- Test Agents (planner/generator/healer) + Playwright MCP exist for AI-driven authoring — this skill still governs what a good spec is; agent output must meet the same gate.

## Quick verify (gate before finishing — applies even when user asked one behavior)

Key landmark render asserted. Happy flow visible outcome. Mutations: request body/query contract checked. Filters/search: emitted params checked. Role gating: allowed + rejected (read-only role sends nothing). Validation: visible error + no/rejected request. Empty and error states where UI has them. Accessible locators throughout; no positional picks, no sleeps, no networkidle. Date-dependent: fixed clock. Touched spec run and green — spec never executed is not deliverable.

## References

- https://playwright.dev/docs/best-practices
- https://playwright.dev/docs/mock
- https://playwright.dev/docs/auth
- https://playwright.dev/docs/test-fixtures
- https://playwright.dev/docs/clock
- https://playwright.dev/docs/aria-snapshots
