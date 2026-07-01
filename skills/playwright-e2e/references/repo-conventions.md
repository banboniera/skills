# Repo Conventions

## Stack

HuggingCar frontend E2E stack:

- React 19
- `@umijs/max`
- Ant Design / ProComponents
- Redux Toolkit + `redux-persist`
- Bun
- Playwright

## Paths

| Thing | Use |
| --- | --- |
| Specs | `e2e/**/*.spec.ts` |
| Config | `playwright.config.ts` |
| Base URL | `http://127.0.0.1:3000` |
| Test dir | `./e2e` |
| Frontend routes | `RouteNames` from `@/utils` |
| Manager auth | `seedReduxState`, `seedManagerSession`, `openManagerPage` |
| Manager API | `openManagerPage` + local `ManagerApiHandler` |

## Commands

Focused E2E:

```bash
BUN_TMPDIR=/tmp/bun bun run test:e2e -- <spec>
```

Direct Playwright:

```bash
BUN_TMPDIR=/tmp/bun bunx playwright test <spec> --reporter=list
```

After E2E/testability edit:

```bash
BUN_TMPDIR=/tmp/bun bun check
```

Before feature finish:

```bash
BUN_TMPDIR=/tmp/bun bun tsc --noEmit
BUN_TMPDIR=/tmp/bun bun run test
BUN_TMPDIR=/tmp/bun bun run test:e2e -- <changed-spec>
```

## Routes

Frontend URL? Use `RouteNames`. No copied route strings. Backend endpoint path in mock may stay literal.

## Auth

Manager spec? No UI-login. Seed persisted auth before `page.goto`.

Login page spec? UI-login OK: login itself under test. Seed auth only for “authenticated user redirected away from login”.
