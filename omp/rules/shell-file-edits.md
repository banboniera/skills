---
description:
  "Edit source files with edit or ast_edit, not sed, perl or Python through bash"
condition:
  - '\bsed\b[^\n|;&]*\s(-[a-zA-Z]*i|--in-place)\b'
  - '\bperl\s+-[a-zA-Z]*i'
  - '\bpython3?\b[\s\S]*?(\.write_text\(|\.write\(|open\([^)]*,\s*\\?["''][wa])'
scope: "tool:bash"
interruptMode: never
---

# Shell file edits

Shell rewrites skip the edit tool's anchors and diff, so a bad pattern silently
corrupts files (non-ASCII text, partial matches, unclosed delimiters) and leaves
no reviewable change.

- One file or a few hunks: use `edit`.
- The same structural change across many files: use `ast_edit`. A plain-text
  rename across many files may use a script, but only after `git status` is
  clean or you have recorded the file list, and review `git diff --stat`
  afterwards.
- Scratch files outside the repository (`/tmp`, reports) are fine.
