---
description: "Use the shop logger instead of console output in src/"
condition:
  - 'console\.(log|debug|info)\('
scope: "tool:edit(src/**/*.ts), tool:write(src/**/*.ts)"
---

Log through `logger` from `src/log.ts` (`logger.info(...)`), not `console`.
