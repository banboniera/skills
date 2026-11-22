---
description:
  Review a file or folder for improvements that prevent incidents and implement
  them. Asks first only about breaking, cross-repo, or irreversible data
  changes. No commit.
argument-hint:
  "<path> [focus: data integrity | security | failure handling | compatibility |
  performance | tests | accessibility]"
---

# Improve

Review $1 and implement improvements a senior reviewer would block a PR over,
or that prevent an incident or user-visible failure. Skip everything else.
Decide independently. Ask before changes that break consumers, change another
repo, or irreversibly change existing data. Give no progress reports.

Focus: $@[2]

## Scope

- `$1` must be a file or folder in a git repo. Ask if missing or ambiguous;
  stop and explain if outside a git repo.
- Review only the target. Fix each qualifying problem everywhere it occurs in
  this repo, including uncommitted code. Preserve the user's work; never stash
  or discard it.
- Focus narrows the review without relaxing these rules. Check every maintained
  target file against every category below. Include test bodies, fixtures,
  test-only harnesses, build scripts, and platform-specific code. Test names
  alone do not establish coverage.

## Review

1. **Data integrity:** lost, duplicated, or corrupted data; missing transactions;
   unsafe retries; races; partial writes.
2. **Security and privacy:** access checks, tenant isolation, trust-boundary
   validation, secrets in code or client bundles, personal data in logs,
   analytics, or storage.
3. **Failure handling:** dependency, network, and input failures; timeouts,
   retries, swallowed or misleading errors; error, loading, and empty states.
4. **Deployed compatibility:** API contracts, response fields, migrations,
   stored and cached data, and clients remaining on old versions, including
   installed mobile apps.
5. **Performance and resources:** queries in loops; unbounded queries, lists,
   caches, or queues; leaked connections, handles, or listeners; repeated hot
   path work; bundle size; startup time. Establish cost from code or measurement.
6. **Critical test gaps:** money, auth, and data flows whose regressions could
   pass unnoticed. Read assertions and fixture preconditions. Check the actual
   outcome; another guard must not mask the condition being tested.
7. **Accessibility:** frontend or mobile core flows blocked for keyboard or
   screen-reader users.

Before judging code, search its usage, tests, config, and string references.
For externally reachable contracts (exports, routes, response fields, events,
queues, env vars, config keys), also search unmerged branches with
`git branch -a --no-merged` and `git grep` on each, and every sibling git repo
in the same parent folder.

Confirm dependency, framework, and platform behavior at the pinned version,
including defaults, timeouts, retries, isolation, escaping, and deprecations.
Use context7 `query-docs` or official docs through `web_search` and `read`;
read installed source if unclear. Skip findings you cannot confirm.

Each improvement needs a concrete trigger in this code and the failure it
prevents. Improve code that works today. Code already wrong for its actual
callers and inputs is a bug: leave it unchanged and report it separately.
Skip style, naming, restructuring for its own sake, dead code, speculative
abstraction, and conditions that cannot occur here.

If nothing qualifies, report "Good as is", what you covered, and any
out-of-scope bugs with file:line and failing scenario. Stop without edits.

## Approval

Ask only for an improvement that:

- **Breaks consumers:** previously working inputs fail or read differently.
  This includes removed or renamed fields, new required inputs, stricter
  validation, changed status or error codes, new response enum values,
  changed stored formats, or published exports.
- **Changes another repo.**
- **Irreversibly changes existing data:** a migration or backfill rewrites or
  deletes data that this work cannot restore.

If none needs approval, implement immediately. Otherwise, before any edits,
make one `ask` call: one form with a radio group per gated improvement. Each
group gives:

- File:line, concrete scenario, and impact.
- The reasonable approaches, then "Leave unchanged". Preselect your
  recommendation; preselection marks it, so don't label it. Each option
  states the change and what breaks, which repos change, or which data
  changes.

Only an approach the user selected and submitted, or approved in chat, is
authorized, and only that approach. "Leave unchanged", an unanswered group,
cancellation, a result that says the form timed out, or no way to ask leaves
that improvement unmade. Implement the independent improvements anyway.

## Implement

- Implement every ungated improvement and approved approach. Approved changes
  to other repos follow these same rules.
- Apply the same bar to discoveries during implementation. Implement ungated
  ones; collect newly gated ones and, after the first pass, ask about them the
  same way, then implement the approved ones.
- **Behavior change:** first write a public-interface scenario test and observe
  its intended failure; implement, then observe it pass. If a test cannot show
  the scenario, use a measurement or user-level run.
- **Missing coverage:** write the test against unchanged, working production
  code and observe it pass. Do not break production to manufacture a red run.
- Extend existing tests where appropriate. Never stash or revert to manufacture
  a failure after implementation.
- Where supported, exercise each change as a user: service request, browser
  page, or emulator screen.
- Skip improvements requiring unavailable secrets, access, or configuration.
  Never invent prerequisites.

## Checks

Run fast checks (lint, types, format check, compiler) after each change or small
group. Run slow checks (suites, builds, end-to-end runs) once at the end,
covering every changed file.

All checks pass before you start; treat failures as introduced by this work.
Change assertions only for intentional behavior changes. Fix other regressions.
If a test pins replaced internals (private helpers, mocks of project modules,
internal call order), rewrite it around the behavior it protects. If an
improvement cannot land without regression, revert only that improvement.

After each fix, rerun fast checks. If slow checks have run, rerun every slow
check covering the fixed files. Repeat until all pass without warnings.

Remove temporary files and stop only processes you started. Leave changes
unstaged and uncommitted. Do not change git state; delete files with `rm`,
not `git rm`.

## Report

Use this order:

1. **Implemented:** each improvement's file:line, prevented scenario, and proving
   test or measurement.
2. **Breaking, cross-repo, or data changes:** file:line and effects. If none,
   say "No breaking changes".
3. **Skipped or reverted:** improvement and reason. Omit user-declined items.
4. **Out-of-scope bugs:** file:line and failing scenario for a separate `verify`.
