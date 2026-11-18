---
description: "No @ts-ignore/@ts-nocheck; @ts-expect-error only with a reason"
condition:
  - "@ts-ignore"
  - "@ts-nocheck"
  - "@ts-expect-error"
scope:
  "tool:edit(**/*.{ts,tsx,mts,cts,astro}),
  tool:write(**/*.{ts,tsx,mts,cts,astro})"
---

# TypeScript type suppression

Do not silence the TypeScript compiler. Fix the type: narrow with
`in`/`typeof`/discriminants, parse untrusted data with the zod schema, correct
the declaration, or fix the generated client input (the OpenAPI schema) instead
of the consumer.

- `@ts-ignore` and `@ts-nocheck`: never.
- `@ts-expect-error`: only where the error is the point (a type-level test) or a
  third-party type bug you verified; write the reason on the same line:
  `// @ts-expect-error: <why>`.
