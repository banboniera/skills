---
description: "Do not mask failing commands in CI, scripts, or containers"
condition:
  - 'continue-on-error:\s*true'
  - '\|\|\s*true\b'
  - '\|\|\s*:\s*$'
  - '\bset\s+\+e\b'
  - '2>\s*/dev/null\s*\|\|'
scope:
  "tool:edit(**/.github/workflows/**), tool:write(**/.github/workflows/**),
  tool:edit(**/*.sh), tool:write(**/*.sh), tool:edit(**/Dockerfile*),
  tool:write(**/Dockerfile*), tool:edit(**/docker-compose*.yml),
  tool:write(**/docker-compose*.yml), tool:edit(**/Makefile),
  tool:write(**/Makefile), tool:edit(**/package.json),
  tool:write(**/package.json), tool:edit(**/scripts/**),
  tool:write(**/scripts/**)"
interruptMode: never
---

# CI failure masking

Masking a failing step makes CI and deploys report success for broken builds.

- Fix the failing command, or make the condition it tolerates explicit (check
  the exit code you expect, test for the file first).
- `|| true` is acceptable only for a command whose failure is a documented,
  expected state (e.g. "already exists"); comment why.
