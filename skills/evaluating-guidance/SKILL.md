---
name: evaluating-guidance
description: >-
  Improves a project's agent harness (AGENTS.md, RULES.md, rules, skills, user
  guidance): checks every claim against code and primary sources, fixes wrong
  guidance and the code built on it, and measures with sandboxed omp trials,
  graded by hidden verifiers, what review cannot settle. Used before adding,
  rewriting or deleting a rule, skill or other agent guidance, when turning
  agent-session failures into eval cases, when asked whether a rule or skill is
  still needed, correct or works, or after model or omp upgrades.
---

# Evaluating guidance

Existing guidance is a hypothesis: a claim stays only if the agent needs it, it is
correct, and nothing better could replace it. Review settles most claims; trials
measure behavior only where review cannot decide and a wrong decision is
expensive. Ask the user once how changes are approved: per round, or applied
autonomously and reported with the full diff at the end.

## Roles

- **Reviewers** (subagents, split by target) judge claims and suggest; they change
  nothing.
- **The root agent** waits for every review, then decides from all evidence what
  to drop, correct, enforce, move or add, including new rules, skills and checks,
  and applies the guidance changes.
- **Fixers** (subagents, split by code area) refactor code built under guidance
  that was dropped or corrected, each fix with a test that proves the correct
  behavior. A fixer may spawn subagents for parts of its area. Guidance problems
  a fixer finds go to the root agent as suggestions; fixers change only code.

Follow the project's own multi-agent and verification rules: who runs builds and
tests, and how changes are integrated.

## 1. Review every claim

Reviewers read each target (AGENTS.md, `.omp/RULES.md`, rules, skills and their
files) claim by claim, in this order:

1. **Needed?** If the agent learns it anyway from code, types, tests or check
   output, or another target already says it, suggest dropping it (or keeping
   one home) and stop there.
2. **Correct?** Check it against the code, tests and configs, and its technical
   premise against current official docs and primary sources; cite both. If it
   is wrong, suggest the correction and list the code built under or around it.
3. **Better?** A test, lint, type or code change that makes the mistake
   impossible; clearer wording per [writing-guidance.md](writing-guidance.md);
   a better home.

Reviewers also mine past sessions for guidance that was ignored or contradicted
and for recurring failures no guidance covers, and suggest new guidance or
checks for them.

## 2. Decide, fix, review again

1. The root agent decides from all reviews and applies the guidance changes.
   A replacing check lands before the guidance it replaces is deleted.
2. Fixers refactor the code built under dropped or corrected guidance and
   report any guidance findings.
3. The root agent verifies the round, then starts a new review of everything the
   round changed, plus the fixers' suggestions.

Repeat until a review finds nothing.

## 3. Measure what review cannot settle

Measure only targets whose mistakes are costly (security, tenancy, money, data
loss, irreversible operations), that cost much context, or that are new
guidance written for a recurring failure.

1. **Set up and size.** Set up the project ([project-setup.md](project-setup.md)),
   write one case, admit it and run it under a small `--budget`. Trial cost and
   time vary a hundredfold between projects. Trials = cases × 2 arms × 3; pick
   the case count from [what a run can detect](decisions.md#what-a-run-can-detect)
   and get the budget approved with these numbers.
2. **Write cases** per [case-authoring.md](case-authoring.md): one per failure
   family, usually 6–10, then admit them. Keep some families out of every run if
   rewrites will need validation later.
3. **Screen** the whole harness against none (`kind = "whole"`). Per-case results
   show which tasks depend on guidance; the aggregate decides only large effects.
4. **Isolate** only where the screen points: `current` vs `minus:<target>` for a
   target whose cases fail without guidance or look harmed; blocks and splits
   when many targets share cases. A rewrite runs as `compare` against the old
   version.
5. **Validate** the final harness against the original on families no run has
   seen. A case seen in any experiment is no longer independent, so a `holdout`
   in project.toml counts only if set before the first run.

The root agent decides from the results with [decisions.md](decisions.md); a
changed target goes back through step 2. Report verdicts, fixes and the full diff
to the user.

## Commands

Run from the project root. `E` selects the installed engine; `S` selects its store.

```sh
E="$HOME/.omp/agent/skills/evaluating-guidance/scripts"
S="$HOME/.cache/guidance-evals/PROJECT"
uv run --project "$E" guidance-evals status --project . --store "$S"
uv run --project "$E" guidance-evals smoke --project . --store "$S"
uv run --project "$E" guidance-evals admit --project . --store "$S"
uv run --project "$E" guidance-evals run EXPERIMENT.toml --project . --store "$S" --budget "$BUDGET"
uv run --project "$E" guidance-evals analyze --project . --store "$S" --experiment NAME
uv run --project "$E" guidance-evals triggers SKILL --project . --store "$S" --budget "$BUDGET"
uv run --project "$E" guidance-evals janitor --store "$S"
```

An experiment TOML sets `name`, `kind` (`whole`, `compare`, `blocks`, `split`,
`holdout`), optional `selectors` (case keys, families or targets) and
`replicates = 3`. For an unresolved comparison, set `replicates = 6` and repeat
`run`; the first three replicates are reused. Repeat `run` to resume. After
judge-only edits, `analyze --project .` regrades without new trials. Execution
changes need a new experiment name. `run --free` is smoke-only evidence.

Any change to the project tree, including code fixes from step 2, invalidates
admissions: re-admit, and update reference patches that no longer apply.

## Rules

- Verdicts use the production model; free or local models only smoke-test.
- Paid runs need a budget the user approved, passed as `--budget`. It counts
  earlier spend of the same frozen plan only; after a case, engine or project
  change, pass the approval minus what earlier plans spent.
- Never select, tune or drop cases because arms did not differ.
- Never read validation results while improving guidance.
- Loads and rule firings are diagnostics, never scores.
