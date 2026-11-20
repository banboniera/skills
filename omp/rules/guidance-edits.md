---
description: "Read the writing criteria before editing agent guidance"
condition:
  - '[\s\S]'
scope: >-
  tool:edit(**/AGENTS.md), tool:write(**/AGENTS.md),
  tool:edit(**/{.omp,omp}/**/{RULES,WATCHDOG}.md),
  tool:write(**/{.omp,omp}/**/{RULES,WATCHDOG}.md),
  tool:edit(**/{.omp,omp}/**/{rules,commands,agents,extensions}/**/*.{md,mdc}),
  tool:write(**/{.omp,omp}/**/{rules,commands,agents,extensions}/**/*.{md,mdc}),
  tool:edit(**/WATCHDOG.{yml,yaml}), tool:write(**/WATCHDOG.{yml,yaml}),
  tool:edit(**/skills/*/**/*.md), tool:write(**/skills/*/**/*.md)
repeatMode: once
---

# Guidance edits

This file is agent guidance. Read `skill://evaluating-guidance/writing.md`,
then redo the edit to meet it.
