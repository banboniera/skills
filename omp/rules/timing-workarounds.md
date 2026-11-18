---
description:
  "No sleeps, zero-delay timers, or processEvents to paper over ordering bugs"
condition:
  - '\btime\.sleep\('
  - '\basyncio\.sleep\('
  - 'new Promise\([^\n]*setTimeout'
  - 'processEvents\('
  - 'QTimer\.singleShot\(\s*0\b'
  - 'setTimeout\([^;]*,\s*0\s*\)'
  - 'requestAnimationFrame\(\s*\(\)\s*=>\s*setTimeout'
scope:
  "tool:edit(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}),
  tool:write(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}), tool:edit(**/*.py),
  tool:write(**/*.py)"
---

# Timing workarounds

Sleeping or deferring "until it works" hides a race; it fails again under load
or on another machine.

- Find the event or state the code is really waiting for and wait on that: a
  signal/slot, a Promise, a query's `isSuccess`, a DB commit
  (`transaction.on_commit`), a serial read with a timeout.
- Qt: never `QApplication.processEvents()` to keep the UI alive; it re-enters
  the event loop. Move blocking work to a `QThread`/`QThreadPool` worker and
  report back with signals.
- A delay is legitimate only for (a) a protocol or device spec requirement (cite
  it), or (b) a polling/backoff interval in a background thread or task, using a
  named constant. Never on the Qt GUI thread or in a request path.
