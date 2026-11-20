---
description:
  "No sleeps or fixed waits in tests; wait on conditions or fake time"
condition:
  - 'waitForTimeout\('
  - '\btime\.sleep\('
  - '\basyncio\.sleep\('
  - '\bsetTimeout\('
  - 'Bun\.sleep\('
  - 'new Promise\(\s*\(?\s*r(esolve)?\s*\)?\s*=>\s*setTimeout'
scope:
  "tool:edit(**/*.{test,spec}.{ts,tsx,mts,js,jsx}),
  tool:write(**/*.{test,spec}.{ts,tsx,mts,js,jsx}),
  tool:edit(**/e2e/**/*.{ts,tsx}), tool:write(**/e2e/**/*.{ts,tsx}),
  tool:edit(**/test/**/*.{ts,tsx}), tool:write(**/test/**/*.{ts,tsx}),
  tool:edit(**/tests/**/*.py), tool:write(**/tests/**/*.py),
  tool:edit(**/test_*.py), tool:write(**/test_*.py), tool:edit(**/*_test.py),
  tool:write(**/*_test.py)"
interruptMode: never
---

# Test real time waits

Fixed waits make tests slow and flaky: they pass on a fast machine and fail in
CI. Check the wait you just wrote.

- Playwright: use web-first assertions (`await expect(locator).toBeVisible()`,
  `toHaveURL`, `expect.poll`) and locator auto-waiting; never
  `page.waitForTimeout`.
- Vitest/Testing Library: `vi.useFakeTimers()` + `vi.advanceTimersByTime()`, or
  `findBy*`/`waitFor` on a real condition.
- Django/pytest: pin the clock with the project's time-machine or freezegun,
  or patch `django.utils.timezone.now`; for Celery and `on_commit` use
  `captureOnCommitCallbacks(execute=True)`; drive hardware through the
  simulator, not delays.
- Fine as written: a timer that runs under fake time, and a temporary probe you
  revert before finishing.
