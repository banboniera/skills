---
description:
  "Never discard uncommitted work, bulk-rewrite a dirty tree, or rewrite shared
  history"
condition:
  - '\bgit\s+reset\b[^\n|;&]*--hard'
  - '\bgit\s+clean\b[^\n|;&]*\s-[a-zA-Z]*f'
  - '\bgit\s+checkout\s+(--\s+)?\.(\s|$|")'
  - '\bgit\s+checkout\b[^\n|;&]*\s--(\s|$)'
  - '\bgit\s+restore\b(?![^\n|;&]*--staged)'
  - '\bgit\s+stash(?:\s|\\t)*((drop|clear|push|save)\b|[|;&"\n]|\\n)'
  - '--allow-dirty\b'
  - '\bgit\s+branch\s+-D\b'
  - '\bgit\s+push\b[^\n|;&]*\s--delete\b'
  - '\bgit\s+push\b[^\n|;&]*\s:\S'
scope: "tool:bash"
---

# Destructive git

This command can destroy work that is not yours: uncommitted changes, untracked
files, stashes, or branches. Unexpected changes in the tree belong to the user.

- Inspect first (`git status`, `git diff`, `git stash list`) and touch only
  files you changed.
- To undo your own edits, revert those specific files or hunks.
- Bulk fixers (`cargo fix` or `clippy --fix --allow-dirty`, scripted rewrites)
  run only on a clean tree or on a file list you write down first. Undo them
  from that list, never by restoring from `HEAD`: the user may have committed or
  edited mid-session.
- Even when the user asked for the command, dry-run it first (`git clean -n`,
  `git status`, `git diff --stat`, `git stash list`). If it would destroy
  anything you did not create in this session, stop: list those exact
  files/changes and get the user's confirmation naming them before running it. A
  general request ("clean up the repo") is not consent to delete a specific file
  the user may not know about.
- If the user confirms, keep a recovery path when possible (`git stash push -u`
  before cleaning, a backup branch before `reset --hard` or `branch -D`).
