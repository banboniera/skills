---
name: playwright-e2e
description: Use when adding, reviewing, or fixing HuggingCar frontend Playwright E2E tests under e2e/, especially @umijs/max routes, React 19 pages, Ant Design UI, Redux-persist auth, API mocks, or Bun Playwright commands.
---

# Playwright E2E

## Core

E2E = user-visible route behavior + deterministic backend contract.

**REQUIRED SUB-SKILL:** Use `playwright-best-practices` for Playwright API rules. This skill = HuggingCar repo rules.

## Read Path

Read exact reference needed:

| Need | Read |
| --- | --- |
| stack, paths, commands, auth route rules | [references/repo-conventions.md](references/repo-conventions.md) |
| coverage choice, spec shape, mocks, locators, Ant Design | [references/e2e-patterns.md](references/e2e-patterns.md) |

If editing E2E/testability, follow verification in repo-conventions. If choosing what to test, follow coverage choice in e2e-patterns.
