---
description: "Fix mypy/pyright errors; ignores must be coded and justified"
condition:
  - '#\s*type:\s*ignore'
  - '#\s*pyright:\s*ignore'
  - '#\s*mypy:\s*ignore'
scope: "tool:edit(**/*.py), tool:write(**/*.py)"
---

# Python type suppression

Fix the type before suppressing it: narrow with `isinstance`/`assert_never`, use
`TypedDict`/`Protocol`/overloads, annotate the queryset or manager generics, or
correct the return type.

- Suppress only a verified stub gap (django-stubs, DRF stubs, PySide6): name the
  exact code and the reason: `# type: ignore[attr-defined]  # stub omits X`. A
  bare `# type: ignore` is never acceptable (mypy `ignore-without-code`, ruff
  PGH003).
- Pyright does not read `# type: ignore` when
  `enableTypeIgnoreComments = false`; it needs `# pyright: ignore[<rule>]`.
- Remove ignores your change made unnecessary.
