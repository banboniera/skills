---
description:
  Delete dead code and simplify a file or folder without changing behavior. Acts
  on its own; no commit.
argument-hint: "<path> [focus: dead code | simplification | duplication]"
---

# Cleanup

Clean up $1: delete dead code, then simplify what remains without changing
behavior. Decide and act on search evidence yourself. Make every justified
cleanup; finding nothing is valid. Work through completion without progress
reports.

Focus: $@[2]. This narrows the work, not the safety rules.

## Start

- If `$1` is not a file or folder in a git repo, stop and say so.
- Start there; apply each cleanup everywhere it applies in the repo.
- Preserve the user's uncommitted changes. Never stash, discard, or delete them.

## Split and repeat

For a target of more than a few files:

1. List the maintained files and split them into slices by module.
2. In one `task` call, give each slice to a read-only subagent, with this
   command's rules in the shared context. Each returns candidates with the
   proof below; none edits.
3. Make the proven changes yourself, or give each slice to one subagent that
   owns its files.
4. Repeat on the files that changed and on any slice not yet reviewed, until a
   round finds nothing that qualifies.

A single file or a small target needs no subagents; still repeat until a round
finds nothing.

## Prove each removal first

For every removal, including props and parameters, complete these searches
before editing, not after reporting:

1. Search this repo: source, tests, config, scripts, build files, and strings.
2. List unmerged branches with `git branch -a --no-merged`; `git grep` each.
3. Search every other git repo in the same parent folder by contract: routes,
   response fields, message/event names, env vars, config keys, and DB columns.

Follow hits through re-exports to live consumers. Dead-code hits and the item's
own tests do not make it used. These also count as uses without a search hit:

- Runtime lookup by name or convention, such as registries, file-based routes,
  and entry points, when the resolving mechanism exists.
- Side-effect imports, including polyfills and styles.
- Signatures fixed by a framework, interface, or callback.

Published exports and public APIs follow these same deletion rules. Report their
removal because consumers outside the searches may break. An unfinished search
is not proof of no consumers.

## Delete

- Unused code, files, dependencies, and their own tests. Remove dependencies with
  the package manager to keep the lockfile in sync.
- Unreachable and commented-out code.
- Redundant tests only when another test fails for every defect they catch.

If a dead-code tool exists in the project, run it for candidates, then prove each
removal as above.

Remove guards or validation only when control flow or enforced runtime constraints
prove they cannot fire. Declared types are not runtime proof. Never touch
migrations or generated code.

## Simplify

- Remove unneeded abstraction and write logic directly.
- Merge logic that must change together; keep independent lookalikes separate.
- Use an existing helper, standard library, platform feature, or installed
  dependency when equivalent. Check the pinned version's behavior for empty/null
  input, errors, ordering, and mutation using context7 `query-docs` or official
  docs via `web_search` and `read`. If unclear, read installed source.

Never add dependencies. Preserve public signatures, outputs, errors, side effects,
log and metric names, and performance. Leave bugs unchanged. Skip cosmetics:
renames, reordering, formatting, and equivalent idioms. Format only changed lines.
Where checks cannot detect a difference, make only rewrites clearly equivalent
by reading.

## Check after editing

All checks pass before cleanup. Do not run baseline checks.

1. After each change or small group, run fast checks: lint, type checks,
   formatter checks, and compilation.
2. At the end, run slow checks covering every changed file: tests, builds, and
   end-to-end runs.
3. A failure belongs to the cleanup. Fix it without changing behavior or revert
   that part. Re-run fast checks. If slow checks have run, also re-run every slow
   check covering the fixed files. Repeat until all pass without warnings.

If a test fails only because it pins simplified internals, rewrite it against
observable behavior. If another test covers that behavior, delete it. Never
weaken observable assertions. Fewer tests must follow these deletion rules.

Finish all required searches and checks before reporting completion. Remove
temporary files; stop only processes you started. Leave changes uncommitted and
unstaged. Delete files with `rm`, not `git rm`; leave other git state unchanged.

## Final response

If the target is invalid, state why you stopped. If a required search or check
cannot run, state the blocker instead of reporting completion.

For a completed cleanup, use exactly one form:

- Nothing changed: `Clean as is`.
- Changes made, none may break unsearched consumers: `No breaking changes`.
- Changes may break unsearched consumers: one entry per change, each containing
  `file:line` and what breaks, such as a deleted published export or public API.
