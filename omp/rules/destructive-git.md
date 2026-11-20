---
description:
  "Never discard uncommitted work, delete untracked files, branches or remote
  refs you did not create, or bulk-rewrite a dirty tree"
condition:
  - '\bgit\s+reset\b[^\n|;&]*--hard'
  - '\bgit\s+clean\b[^\n|;&]*\s(-(?![a-zA-Z]*n)[a-zA-Z]*f|--force\b)'
  - '\bgit\s+checkout\s+(--\s+)?\.(\s|$|")'
  - '\bgit\s+checkout\b[^\n|;&]*\s--(\s|$)'
  - '\bgit\s+restore\b(?![^\n|;&"]*--staged)[^\n|;&"]*([|;&"\n]|\\n)'
  - '\bgit\s+stash(?:\s|\\t)*((drop|clear|push|save)\b|[|;&"\n]|\\n|$)'
  - '--allow-dirty\b'
  - '\bgit\s+branch\s+-D\b'
  - '\bgit\s+push\b[^\n|;&]*\s--delete\b'
  - '\bgit\s+push\b[^\n|;&]*\s:\S'
  - '(/|\brtk\s+)git\s+(checkout|switch)\b'
scope: "tool:bash"
repeatMode: always
---

This command can destroy work that is not yours: uncommitted changes, untracked
files, stashes, branches or remote refs.

`bash.gitGuard` refuses stash, `reset --hard`, restore, checkout and switch in a
main checkout. In a linked worktree they run after saving the discarded changes
to `refs/omp/discarded`; that is a recovery path, not the user's consent. Calling
git by path (`/usr/bin/git`) or through a wrapper (`rtk git`) skips the guard:
run plain `git`.

- Inspect first (`git status`, `git diff`, `git clean -n`, `git branch -v`) and
  touch only files you changed. To undo your own edits, revert those hunks with
  the edit tool.
- If the command would destroy anything you did not create in this session,
  stop: list those exact files, changes or branches and get the user's
  confirmation naming them. A general request ("clean up the repo") is not
  consent to delete a file the user may not know about.
- If the user confirms, keep a recovery path: copy the files `git clean -n`
  lists out of the tree, and create a backup branch before `branch -D`.
- Bulk fixers (`cargo fix` or `clippy --fix --allow-dirty`, scripted rewrites)
  run only on a clean tree or on a file list you write down first. Undo them
  from that list, never by restoring from `HEAD`: the user may have committed
  or edited mid-session.
