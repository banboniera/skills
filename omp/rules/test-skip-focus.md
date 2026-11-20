---
description: "Never skip, focus, or xfail tests to get a green run"
condition:
  - '\b(it|test|describe|bench|suite)\.(skip|only|todo|fixme|fails)\b'
  - '(?<![\w.])(?<!function )[xf](it|describe|test)\('
  - '(?m)^[ \t]*@(unittest\.)?skip\b'
  - '\.skipTest\('
  - 'pytest\.mark\.(skip|xfail)\b'
  - 'pytest\.(skip|xfail)\('
scope:
  "tool:edit(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}),
  tool:write(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}), tool:edit(**/*.py),
  tool:write(**/*.py)"
interruptMode: never
---

# Test skip focus

A failing test is information: fix the code, or fix the test if it asserts the
wrong behavior.

- Never `.only`/`fit`/`fdescribe`: they silently disable the rest of the suite.
- Never `.skip`/`xfail`/`@skip`/`test.fixme` to make a run pass.
- A platform or environment condition (no display, no serial device) is fine
  only with a precise condition and reason, e.g.
  `skipUnless(shutil.which("x"), "needs x")`.
