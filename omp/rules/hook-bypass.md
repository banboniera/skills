---
description: "Never bypass git hooks, signing, or force-push"
condition:
  - "--no-verify"
  - '\bgit\s+commit\b[^\n|;&]*\s-[a-zA-Z]*n'
  - '\bHUSKY=0'
  - "--no-gpg-sign"
  - '\bpush\b[^\n|;&]*\s(-f\b|--force(?=[\s"|;&\\]))'
scope: "tool:bash"
repeatMode: always
---

# Hook bypass

Hooks and signing are the repo's quality gate. If a hook fails, fix what it
reports; do not bypass it.

- Never `--no-verify`, `-n`, `HUSKY=0`, or `--no-gpg-sign`.
- Never force-push; if history must be rewritten on your own branch and the user
  asked for it, use `--force-with-lease`.
