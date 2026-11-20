---
description:
  "Fix lint findings; never suppress lint for a file, range, group or every
  rule"
condition:
  - '(?m)^[ \t]*(?://|\{?/\*+|\*)[ \t]*biome-ignore-(?:all|start)[ \t]+lint(?=[:/ \t])'
  - '(?m)^[ \t]*(?://|\{?/\*+|\*)[ \t]*biome-ignore[ \t]+lint(?:/[A-Za-z0-9_-]+)?[ \t]*:'
  - '(?m)^[ \t]*(?://|\{?/\*+|\*)[ \t]*eslint-disable(?=[ \t]|\*/)'
  - '(?m)^[ \t]*(?://|\{?/\*+|\*)[ \t]*fallow-ignore-file[ \t]*(?:--|\*/|\n)'
scope:
  "tool:edit(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}),
  tool:write(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}),
  tool:edit(**/*.{json,jsonc,css}), tool:write(**/*.{json,jsonc,css})"
interruptMode: never
---

# JavaScript lint suppression

This comment switches lint off for a whole file, a range, a rule group or every
rule. A lint finding is a defect report: fix the code.

- If one rule is wrong for one line, suppress that rule on that line and give
  the reason:
  `// biome-ignore lint/<group>/<rule>: <why this is correct>`,
  `// eslint-disable-next-line <rule> -- <why>`,
  `// fallow-ignore-next-line <issue-type> -- <why>`.
- Formatter directives (`biome-ignore format:`, `prettier-ignore`) are not lint
  suppressions.
