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

Existing guidance is a hypothesis. A claim stays only if it is correct, the agent
needs it, and no test, lint, type or code change could enforce it instead. Most
claims are settled by review; trials measure behavior only where review cannot
decide and a wrong decision is expensive. Nothing in the project changes without
the user's approval.

## 1. Review every claim

Read each target (AGENTS.md, `.omp/RULES.md`, rules, skills and their files) claim
by claim and decide:

- **Correct?** Check it against the code, tests and configs; check its technical
  premise against current official docs and primary sources. Cite both.
- **Needed?** The agent learns it anyway from code, types, tests or check output,
  or another target already says it: delete or keep one home.
- **Best form?** A test, lint, type or code change that makes the mistake
  impossible replaces the guidance. Otherwise rewrite it per
  [writing-guidance.md](writing-guidance.md).

Mine past sessions for guidance that was loaded, ignored or contradicted, and for
recurring failures no guidance covers: those are candidates for new guidance.

## 2. Fix, then review again

Wrong guidance leaves wrong code. For every claim found incorrect, search the
code for what was built under it or around it. Fix the guidance and that code
together, each code fix with a test that proves the correct behavior; land
replacing checks before deleting the guidance they replace. Then review the
changed guidance and code again, and repeat until a pass finds nothing. Follow
the project's own verification and multi-agent rules while fixing.

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

Decide with [decisions.md](decisions.md). Report verdicts, fixes and the diff to
the user.

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
