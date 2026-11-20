---
description:
  Find bugs in a file or folder by checking every caller, reproduce them, and
  fix them. Asks first only about breaking, cross-repo, irreversible data, or
  unproven fixes. No commit.
argument-hint:
  "<path> [focus: wrong results | errors | races | data loss | timeouts |
  consumers]"
---

# Verify

Find bugs in $1, reproduce each one, and fix them. A bug means code that is
wrong for its real callers and reachable inputs. Finding nothing is valid.
Decide everything yourself except the fixes requiring approval below. Work
through to the final report without progress updates.

Focus (narrows the work, never relaxes these rules): $@[2]

## Scope

- `$1` must be a file or folder in a git repo. Ask if it is missing or ambiguous.
  If it is outside a git repo, stop and say so.
- Verify the target, not the whole repo. Also handle bugs encountered in callers
  you read and occurrences of the same bug elsewhere in the repo.
- Include uncommitted target changes. Fixes elsewhere in the repo also apply to
  uncommitted code. Never stash or discard the user's changes.

## Find

Check every maintained target file for all of these:

- wrong results;
- mishandled reachable inputs, including malicious inputs at exposed trust
  boundaries even when legitimate callers never send them;
- errors swallowed or surfaced wrongly;
- broken state transitions;
- data lost, duplicated, or exposed to the wrong user or tenant;
- races and missing transactions;
- external calls without timeouts or failure handling;
- mismatches with consumers.

Style, naming, and hardening against unreachable inputs are not bugs.

For each candidate:

1. Trace callers and inputs through this repo, including tests, config, and
   string references. For external contracts (package exports, routes, response
   fields, events, queues, env vars, config keys), also search unmerged branches
   (`git branch -a --no-merged`, then `git grep` each) and every other git repo
   in the same parent folder. Check how those consumers use the contract.
2. Confirm dependency, framework, or platform behavior at the pinned version:
   defaults, timeouts, retries, isolation, escaping, and deprecations. Use
   context7 `query-docs` or official docs through `web_search` and `read`. If
   unclear, read the installed package source. Do not rely on memory.

## Reproduce

Before fixing, write and run each candidate's regression test through the
public interface. Use a probe only when a test cannot express the scenario.
Classify the evidence:

- **Proven:** fails for the intended reason, the input is reachable from a real
  caller, consumer, or exposed trust boundary, and the expected result follows
  from a contract, docs, a dependent consumer, or stated code intent.
- **Suspected:** fails with assumed reachability or expected behavior; still
  passes after checking the test and setup; or cannot reproduce on demand.
  State each assumption and the evidence needed to settle it.
- **Dropped:** docs, source, or real callers contradict the candidate.

A failing test alone does not prove a bug. Keep classified test expectations
fixed. If the test is wrong, correct it and classify the candidate again.

If nothing is proven or suspected, remove your dropped-candidate tests, report
"No bugs found" with coverage, and stop.

## Ask only when needed

A fix requires approval if any of these applies:

- The bug is suspected or the right behavior needs a product decision.
- It changes consumer-visible behavior that previously worked: removed or
  renamed fields, new required inputs, stricter validation, changed status or
  error codes, new response enum values, stored formats, or published exports.
  Restoring a documented contract does not waive this gate: compare the actual
  before/after behavior, including behavior that was buggy.
- It changes another repo.
- It irreversibly rewrites or deletes existing data, including through a
  migration or backfill.

If no fix requires approval, start fixing. Otherwise, after reproduction and
before any fixes, make one `ask` call: one form with a radio group per gated
fix. Each group gives:

1. File:line, failure, triggering caller/input, and evidence. For suspected bugs,
   include the assumptions and what would settle them.
2. The reasonable fixes, recommendation first and labelled as recommended, then
   "Leave unfixed". Each option states its behavior changes, consumer breaks,
   affected repos, and irreversible data changes as applicable.

Preselect nothing. Only a fix the user selected and submitted, or approved in
chat, is authorized. "Leave unfixed", an unanswered group, cancellation, a
result that says the form timed out, or no way to ask leaves that bug unfixed.
Continue with the other fixes.

## Fix

- Fix every proven bug needing no approval and every approved fix. Approved
  fixes may change other repos under these same rules.
- Fix the root cause for the best end state, not the smallest diff. Fix shared
  code rather than patching one caller; update all affected callers and tests
  that assert the buggy behavior.
- A fix is complete when its regression test passes or its probe stops showing
  the defect. If the test never failed or only a probe exists, also exercise
  the fix as a user would and retain public-interface test coverage.
- Reproduce bugs discovered during fixes too. Collect newly gated fixes; after
  the first pass, ask about them using the same format and apply approved ones.
- Skip fixes needing unavailable secrets, access, or config values. Never
  invent them.

## Checks and cleanup

- Run fast checks (linter, type checker, formatter check, compiler) after each
  fix or small group.
- Run slow checks (test suites, builds, end-to-end runs) once at the end,
  covering every changed file.

All checks passed before you started; every failure is yours. Change behavior
assertions only for an intentional behavior change. Rewrite tests pinned only
to changed internals (private helpers, own-module mocks, internal call order)
against the behavior they protect. Never weaken other observable assertions.
Fix every other regression; revert a fix that cannot land without one.
After each correction, rerun fast checks and any already-run slow checks
covering the corrected files. Repeat until every check passes without warnings.

Choose test cleanup by the final disposition, not the filename:

- **Fixed:** retain regression coverage, including public-interface tests for
  approved suspected or probe-only fixes. A passing probe test is not scratch.
- **Unfixed** (dropped, declined, skipped, or reverted): remove the reproduction
  tests you introduced for that candidate.

Remove temporary files and stop only processes you started. Leave changes
uncommitted and unstaged. Do not change git state; delete files with `rm`, not
`git rm`.

## Report

1. List each applied fix: file:line, the failing scenario, and the regression
   test or probe that proves it.
2. List applied fixes that break consumers, change other repos, or irreversibly
   change data, with file:line and impact. If none, say "No breaking changes".
3. List skipped or reverted bugs with reasons. Omit bugs the user declined.
