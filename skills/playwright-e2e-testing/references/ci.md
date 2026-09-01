# Configuration & CI

## Config baseline

```ts
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,          // committed .only silently skips suite
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['html'], ['github']] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:9000',
    trace: 'on-first-retry',             // full trace exactly when it matters
  },
  webServer: {
    command: 'npm run build && npm run preview',
    url: 'http://127.0.0.1:9000',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
})
```

- `workers: 1` in CI = stability default on shared runners; powerful self-hosted runners can raise — measure, don't guess.
- `reuseExistingServer: !CI` speeds local loops but can run against **stale build** — rebuild before trusting surprising local pass.
- `expect: { timeout }` raised globally only for legitimately slow app shell.
- Browser matrix via `projects` + `devices` when cross-browser is real requirement; one Chromium project fine default until then.

## GitHub Actions shape

```yaml
- uses: actions/setup-node@v6        # or oven-sh/setup-bun@v2
- run: npm ci
- run: npx playwright install --with-deps chromium
- run: npx playwright test
- uses: actions/upload-artifact@v7
  if: ${{ !cancelled() }}
  with:
    name: playwright-report
    path: playwright-report/
```

- Install only browsers you test (`chromium`), not all three. Headless-only CI: `npx playwright install --only-shell` (chromium headless shell — smaller, faster install).
- Upload report on failure **and** flaky-pass — `!cancelled()`, not `failure()`.
- `maxFailures: 1` in CI fails fast on broken deploy; omit locally.

## Sharding (when one job too slow)

```yaml
strategy:
  matrix: { shard: [1/4, 2/4, 3/4, 4/4] }
steps:
  - run: npx playwright test --shard=${{ matrix.shard }}
```

- With `fullyParallel`, balancing per-test — even distribution.
- Reporters across shards: `blob` reporter per shard, upload, `npx playwright merge-reports --reporter html ./all-blob-reports` in final job. Without merging: N partial HTML reports.

## Artifacts policy

| Artifact | Setting | Why |
|----------|---------|-----|
| Trace | `on-first-retry` | Free on green runs, complete on run you need |
| Screenshot | `only-on-failure` | Quick glance before opening trace |
| Video | usually off | Big, rarely more useful than trace |

## Local commands worth knowing

```sh
npx playwright test path/to.spec.ts        # touched spec only — default loop
npx playwright test --ui                   # watch mode, time-travel
npx playwright test --debug                # inspector
npx playwright test -g "filters orders"    # by title
npx playwright test --repeat-each=5        # flake proof
npx playwright test --last-failed          # rerun only last run's failures
npx playwright show-report                 # last HTML report
npx playwright show-trace <trace.zip>      # answer to "what actually happened"
```

Substitute project's package runner (`bun run test:e2e`, etc.) when scripts exist — check `package.json` first.
