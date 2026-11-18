---
description: "No double casts or non-null assertions to bypass the type checker"
astCondition:
  - "$X!"
  - "$X as unknown as $T"
scope:
  "tool:edit(**/*.{ts,tsx,mts,cts,astro}),
  tool:write(**/*.{ts,tsx,mts,cts,astro})"
---

# TypeScript unchecked assertions

`as unknown as T` and `value!` tell the compiler to trust an unchecked claim;
when it is wrong the bug surfaces at runtime, far from the cause.

- Narrow instead: a type guard, an early return/throw on `null`/`undefined`, a
  zod parse at the trust boundary, or a correctly typed factory in tests.
- If the types are wrong upstream (generated client, library types), fix them
  there.
- Keep an assertion only when you can state why it is always true; put that
  reason in a comment on the line.
