---
description: "Raw-HTML sinks need trusted, escaped input"
condition:
  - "dangerouslySetInnerHTML"
  - "set:html"
  - '\.(inner|outer)HTML\s*='
  - 'insertAdjacentHTML\('
  - 'document\.write\('
  - '\bmark_safe\('
  - '\|\s*safe\b'
scope:
  "tool:edit(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}),
  tool:write(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}), tool:edit(**/*.py),
  tool:write(**/*.py), tool:edit(**/*.html), tool:write(**/*.html)"
interruptMode: never
---

# HTML injection sinks

This renders raw HTML. Use it only with content you control or have sanitized.

- Prefer normal rendering (JSX text, Astro expressions, Django autoescape,
  `format_html`).
- JSON-LD in `<script type="application/ld+json">`: serialize trusted data with
  `JSON.stringify` and escape `<` as `\u003c`.
- Never pass user, API, or translated content through it unsanitized.
