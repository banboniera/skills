---
description:
  "Fix lint findings instead of biome-ignore / eslint-disable / fallow-ignore"
condition:
  - "biome-ignore"
  - "eslint-disable"
  - "fallow-ignore"
  - "prettier-ignore"
scope:
  "tool:edit(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}),
  tool:write(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}),
  tool:edit(**/*.{json,jsonc,css}), tool:write(**/*.{json,jsonc,css})"
---

# JavaScript lint suppression

A lint finding is a defect report; fix the code.

- `lint/correctness/useExhaustiveDependencies`: a missing dependency is a
  stale-closure bug. Add the dependency, move the logic out of the effect, or
  use `useEffectEvent` (React 19.2+) for non-reactive logic. Do not suppress.
- `lint/suspicious/noExplicitAny`, `noNonNullAssertion`: see the type rules;
  narrow or parse instead.
- If the rule is genuinely wrong for this line, suppress only that rule on that
  line, with a real reason:
  `// biome-ignore lint/<group>/<rule>: <why this is correct>`. Never
  `biome-ignore-all`, a range, or a whole group.
- Never turn the rule off in `biome.jsonc` to make one case pass.
