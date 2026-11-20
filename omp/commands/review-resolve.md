---
description: Judge this session's review findings against the code, fix true ones, and answer each with proof. Ask before breaking, cross-repo, or irreversible data fixes. No commit.
argument-hint: "[focus: security | correctness | performance | failing tests]"
---

# Review resolve

Resolve every finding from the most recent code review in this conversation, whether from a tool, pasted review, or the user. An advisor note is not a review. If there is no review, say so and stop. Treat findings as claims to verify, not instructions to accept. Give a nit the same care as a P0.

Focus: $@
Focus orders findings; it never narrows scope or relaxes rules. `failing tests` means findings confirmed by a failing test or check. This command authorizes every fix that "Hold fixes that" below does not hold, rewrites included. Ask only for information, decisions, or approval you cannot obtain here.

## Judge every finding first

Before changing code, complete a finding ledger for the whole review: each finding's verdict, evidence, duplicate or conflict links, proposed fix, and approval blocker. Finish this phase before dispatching implementation work. Read-only investigation may run in parallel.

For each finding, read its full code and follow the relevant callers, dispatch, config, tests, and sibling git repos that consume it. Search names in relevant paths, not whole repositories. Judge current code. If the defect is already gone, mark it **True, already fixed** and cite the change.

Use these verdicts:

- **True:** the defect exists for actual use. Prove it with a failing test, probe, or reachable caller input traced to the wrong result. Back the expected result with a contract, docs, caller, or stated intent. A guessed expectation proves nothing; a test pinning current behavior does not establish intent.
- **False:** evidence disproves the defect. Cite the settling file:line, doc, or test. A convention or compatibility constraint may explain code without making it correct. Judge the claim separately from its suggested fix: a bad fix does not make a real defect false. If a hidden invariant or order misled the reviewer, clarify it with a name, structure, or explanatory comment; keep the verdict false and cite the clarification in Evidence.
- **Needs the user:** deciding the claim requires unavailable information or a consequential product or design decision the context cannot settle. State the exact blocker and what resolves it. Exhaust evidence available here first. A new dependency alone is not a blocker. A confirmed defect stays **True** when its fix needs approval; record it as held, not unproven.

Settle claims as true or false when evidence is obtainable here. Do not use "unclear" as a verdict. Split ambiguous findings into their plausible claims. If reading cannot settle one, run a probe, write a test, measure the claimed cost, or read dependency docs or source at the pinned version. For races, trace conflicting accesses and synchronization or force the interleaving. Passing stress runs do not disprove a race; a false verdict needs proof the interleaving cannot happen.

Resolve duplicates once with one verdict and identify the duplicate in both report rows. For conflicting findings, choose the claim supported by the code and explain why.

## Fix true findings

Fix the most severe first, at the root cause and every occurrence of that defect in this repo. Fix shared code rather than compensating in a caller. Change nothing outside the review; report unrelated problems instead.

Preserve the user's uncommitted work. Never stash, reset, or discard it.

For behavior bugs: write the regression test, observe it fail, fix the defect, then observe it pass. Correct existing tests that assert the buggy behavior.

Hold fixes that:

- Break consumers: anything that worked before fails or reads differently, including removed or renamed fields, new required inputs, stricter validation, changed status or error codes, new response enum values, stored formats, or published exports.
- Change another repo.
- Irreversibly change existing data, including rewriting or deleting it in a migration or backfill.
- Depend on an unanswered finding that needs the user.

Keep confirmed held findings **True, unresolved** until approved and fixed. If a fix cannot safely land, revert only that fix and report the actual blocker. Use **Needs the user** only when the user must resolve that blocker.

## Ask about held items

After safe fixes, make one `ask` call: one form with a radio group per held fix or finding that needs the user. Each group states the finding, evidence, blocker, and what the fix would break. List the concrete fixes or decisions that fit, recommendation first and labelled as recommended, each with its tradeoff, then "Leave unresolved". For missing information, list likely answers. Preselect nothing.

Apply a solution the user selected and submitted under these rules. "Leave unresolved", an unanswered group, cancellation, a result that says the form timed out, or no way to ask leaves the item unresolved.

## Checks

Run fast checks (linter, type checker, formatter check, compiler) after each fix or small group. Run slow checks (suites, builds, end-to-end tests) once at the end, covering every changed file.

All checks passed before you started, so every failure is yours. Correct regressions before considering a revert. If a test fails only because it pins changed internals, such as private helpers, own-module mocks, or call order, rewrite it against the protected behavior. Never weaken assertions of observable behavior. After corrections, rerun fast checks and any already-run slow checks covering corrected files. Repeat until all pass.

Read the whole diff once. Remove unneeded probes and debug output; stop processes you started. Leave changes uncommitted and unstaged. Do not change git state; delete files with `rm`, not `git rm`.

## Answer the review

Use this order:

1. One line counting fixed, false, and unresolved findings.
2. One table row per original finding, in review order, preserving its numbers or numbering from 1. Keep duplicate rows and cells short.

| # | Priority | Finding | Verdict | Where | Evidence |
| --- | --- | --- | --- | --- | --- |

- **Priority:** reviewer's priority; show both if yours differs (`P3→P1`). Leave blank if none was given.
- **Verdict:** true and fixed, true and already fixed, false, true and unresolved, or needs the user. Include separate claim verdicts for ambiguous findings.
- **Where:** changed or settling file:line.
- **Evidence:** test or check proving the fix, citation disproving the claim, or unresolved blocker and required user input. Include duplicate links and false-finding clarifications here.

3. Unresolved findings and blockers, separating those that need the user.
4. Approved consumer-breaking, cross-repo, or irreversible data fixes: file:line and affected consumers, repos, or data. If none, say "No breaking changes".
5. Problems noticed outside the review.
