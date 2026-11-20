---
description: "Never swallow errors; handle them or let them propagate"
condition:
  - 'catch\s*(\([^)]*\))?\s*\{\s*\}'
  - 'except[^:\n]*:\s*\n\s*(pass|\.\.\.|continue)\b'
  - 'except\s*:'
  - 'except\s+(Base)?Exception\b'
astCondition:
  - "$P.catch(() => {})"
  - "$P.catch(($E) => {})"
  - "$P.catch($E => {})"
  - "$P.catch(() => null)"
  - "$P.catch(() => undefined)"
  - "$P.catch(() => [])"
  - "$P.catch(() => false)"
  - "$P.catch(console.log)"
  - "$P.catch(console.error)"
  - "$P.catch(console.warn)"
  - "$P.catch(noop)"
  - "suppress(Exception)"
  - "suppress(BaseException)"
scope:
  "tool:edit(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}),
  tool:write(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}), tool:edit(**/*.py),
  tool:write(**/*.py)"
interruptMode: never
---

Check the handler you just wrote.

- Catch only the specific exception type you expect, at the level that can act
  on it: show the user feedback, return a typed fallback, retry a
  known-transient operation, or translate it to a domain error.
- Unexpected errors must propagate to whatever reports them. Do not
  log-and-continue.
- Not swallowing: a handler that re-raises, wraps (`raise X from e`), or hands
  the failure to the caller.
- If ignoring a specific failure is correct, catch that exact type and write why
  on the line.
- A temporary probe or mutation you revert before finishing needs no change.
