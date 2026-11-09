---
name: evaluating-guidance
description: >-
  Improves a project's agent harness (AGENTS.md, RULES.md, rules, skills, user
  guidance) by measuring what each piece changes in real work: sandboxed omp
  trials with and without it, graded by hidden verifiers. Used before adding,
  rewriting or deleting a rule, skill or other agent guidance, when turning
  agent-session failures into eval cases, when asked whether a rule or skill is
  still needed or works, or after model or omp upgrades.
---

# Evaluating guidance

Guidance stays only if the agent finishes real work more correctly, safely or
cheaply with it. Decide as much as possible without trials; spend trials only
where a wrong decision is expensive. The engine in `scripts/` runs the trials.

## Workflow

1. **Review without trials.** Existing guidance is a hypothesis, not a given:
   each claim may be wrong, unneeded or a workaround for a better fix. For every
   claim, check:
   - **Correct?** Verify it against the code, tests and configs, and its
     technical premise against current official docs and primary sources.
   - **Needed?** Delete it if the agent learns it from code, types, tests or
     check output, or if another target already states it.
   - **Best form?** A test, lint, type or code change that makes the mistake
     impossible beats any wording; then the guidance goes. Otherwise rewrite
     per [writing-guidance.md](writing-guidance.md).

   Read past sessions for guidance that was loaded, ignored or contradicted, and
   for recurring failures no guidance covers; those are candidates for new
   guidance. Most decisions end here; trials settle only what review cannot.
2. **Choose what to measure.** Only targets whose mistakes are costly (security,
   tenancy, money, data loss, irreversible operations) or that cost much
   context, and new guidance written for a recurring failure.
3. **Size before building.** Set up the project ([project-setup.md](project-setup.md)),
   write one case, admit it, and run it with a small `--budget`. Cost and time
   per trial vary a hundredfold between projects. Trials = cases × 2 arms × 3;
   choose the case count from [what a run can detect](decisions.md#what-a-run-can-detect)
   and get the budget approved with these numbers.
4. **Write the cases** ([case-authoring.md](case-authoring.md)), one per failure
   family, usually 6–10, and admit them.
5. **Screen: whole harness vs none** (`kind = "whole"`). Per-case results show
   which tasks depend on guidance; the aggregate decides only large effects.
6. **Go deeper only where the screen points:** compare `current` with
   `minus:<target>` when a target's cases fail without guidance or look harmed.
   Blocks and splits are for many targets sharing cases.
7. **Decide** with [decisions.md](decisions.md); rewrite per
   [writing-guidance.md](writing-guidance.md). Confirm a rewrite against the
   original on families no earlier run has observed: cases kept out of every
   experiment so far, or fresh ones. A case seen in a screen is no longer
   independent, so `holdout` in project.toml helps only if set before the first
   run. Give the user the report and diff; change nothing without approval.

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
`run`; the first three replicates are reused.

Repeat `run` to resume: complete trials are skipped. After judge-only edits,
`analyze --project .` regrades saved artifacts without agent trials. Execution
changes need a new experiment name. `run --free` is smoke-only evidence.

## Rules

- Verdicts use the production model; free or local models only smoke-test.
- Paid runs need a budget the user approved; pass it as `--budget`. It counts
  spend already made by the same frozen plan, so a resumed run stays within it.
  A changed case, engine or project starts a new plan that cannot see earlier
  spend: pass the approval minus what earlier plans spent.
- Never select, tune or drop cases because arms did not differ.
- Never read holdout results while improving guidance.
- Loads and rule firings are diagnostics, never scores.
