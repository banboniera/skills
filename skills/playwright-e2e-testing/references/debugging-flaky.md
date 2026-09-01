# Debugging & Flaky Tests

## Failure workflow

1. **Run one failing spec**, line reporter: `npx playwright test path/to.spec.ts --reporter=list`.
2. **Read error** — Playwright errors specific: which locator, how many matches, what state it waited for.
3. **Trace**: `--trace on` locally, then `npx playwright show-trace test-results/.../trace.zip` — timeline, DOM snapshots per action, network, console. Trace answers "what did page actually look like"; never guess.
4. Targeted debugging: `--debug` (inspector, step through), `--ui` (watch mode), `page.pause()` at suspect line.
5. Many failures: `--last-failed` reruns only previous failures. **Prove stability** after fixing flake: `npx playwright test path/to.spec.ts --repeat-each=5`.

## Flake taxonomy — root causes, not symptoms

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| Passes alone, fails in suite | Shared state / ordering dependency | Isolate: per-test seed, no module-level mutables, unique data per worker |
| Fails ~monthly / some machines | Real clock or timezone in test data | `page.clock.setFixedTime()`; never compute expected values from `new Date()` |
| Click "did nothing" | Hydration race — listeners not attached | Product fix: disable control until hydrated |
| Element not found intermittently | Render race + non-retrying assertion | Web-first assertion; check for `isVisible()`-into-sync-expect |
| Wrong element intermittently | Positional locator (`.nth`, `.first`) after reorder | `.filter()` by content |
| Request assertions intermittently empty | Asserting recorded requests before they land | `expect.poll` on record array |
| Drag/click lands wrong | Coordinate math (`boundingBox` + mouse) | `locator.dragTo()` / locator-based actions; coordinates only when widget offers nothing else, assert outcome not gesture |
| Mock not applied | Route registered after `goto`, or service worker shadowing | Register before navigation; `serviceWorkers: 'block'` |
| Animation mid-flight screenshots/clicks | CSS transitions | Playwright waits for stability; screenshots: `animations: 'disabled'` |

## Deterministic time

```ts
await page.clock.setFixedTime(new Date('2026-03-15T10:00:00'))   // before goto
await page.goto('/calendar')
```

- `setFixedTime` — recommended: `Date.now()`/`new Date()` frozen, timers still run.
- `clock.install()` — full control (pause, `fastForward`, `runFor`) for timer-driven UI; **must be called before any other clock API**.
- Test data with dates: derive from same fixed instant page sees, never machine clock. Timezone-sensitive suites: pin `timezoneId` in `use`.

## Retries — diagnosis, not medicine

- `retries: process.env.CI ? 2 : 0` — bounded in CI, zero locally.
- Test passing on retry reported **flaky**, not passed. Flaky = failed-with-clue: open retry trace (`trace: 'on-first-retry'` makes this free).
- Never raise retries to make suite green. Every retry hides real race that eventually lands in production timing.
- 1.62 `retryStrategy: 'isolated'`: defers retries, runs without sibling interference — distinguishes "test racy" from "suite interfering".

## Console/page errors as signal

Smoke-level suites: collect `page.on('console')` (errors only) and `page.on('pageerror')`, assert empty at end. Catches broken bundles, runtime exceptions no locator assertion sees. Explicit allowlist for known third-party noise — not blanket filter.

## Timeouts

Default action/assertion timeouts usually right. Test needing longer timeout is telling you something — slow webServer build, missing mock, wrong readiness signal. Raise `expect.timeout` globally only for legitimately slow app shell; per-assertion `{ timeout }` for one known-slow operation, with comment.
