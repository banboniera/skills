---
description: "Fix ruff findings instead of noqa; complexity codes mean refactor"
condition:
  - '#\s*noqa'
  - '#\s*ruff\s*:\s*noqa'
scope: "tool:edit(**/*.py), tool:write(**/*.py)"
---

# Python lint suppression

Fix the finding. A ruff code is a defect report, not noise.

- Complexity codes (C901, PLR0911, PLR0912, PLR0913, PLR0915) mean the function
  does too much: split it or introduce a parameter object. Do not suppress them
  in new code.
- Security codes (S...) mean a real risk: fix it.
- If the finding is genuinely wrong for this line, use the exact code and a
  reason: `# noqa: S105 - fixed CI-only key`. Never a bare `# noqa` (PGH004) or
  a file-level `# ruff: noqa`.
- Never add the code to `ignore`/`per-file-ignores` in `pyproject.toml` to make
  one case pass.
