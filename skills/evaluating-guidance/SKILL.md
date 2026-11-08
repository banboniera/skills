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
cheaply with it. The engine in `scripts/` measures that; this skill turns the
results into keep, fix, delete or convert decisions.

## Workflow

1. Set up the project once: [project-setup.md](project-setup.md).
2. Inventory each target: claims the agent cannot infer from code, tests or
   compiler; what past sessions show it loaded, ignored or contradicted; whether
   current docs and web sources confirm its technical claims. Turn enforceable
   claims into tests or lints. Recurring failures no guidance covers are
   candidates for new guidance.
3. Write cases from real failures ([case-authoring.md](case-authoring.md)) and
   admit them.
4. Run the layers in order, each only for what is still open: free checks, whole
   harness, blocks, splits, holdout.
5. Decide with [decisions.md](decisions.md). For harm, unloaded or still-failing
   targets, rewrite per [writing-guidance.md](writing-guidance.md); keep only
   measured wins over the old version on dev cases.
6. Validate the final harness against the original on the holdout; give the user
   the report and diff. Change nothing without approval.

## Commands

Run from the project root. `E` selects the installed engine; `S` selects its store.

```sh
E="$HOME/.omp/agent/skills/evaluating-guidance/scripts"
S="$HOME/.cache/guidance-evals/PROJECT"
uv run --project "$E" guidance-evals status --project . --store "$S"
uv run --project "$E" guidance-evals smoke --project . --store "$S"
uv run --project "$E" guidance-evals admit --project . --store "$S"
uv run --project "$E" guidance-evals triggers SKILL --project . --store "$S" --budget "$BUDGET"
```

Each experiment TOML sets `name`, `kind`, selectors and a balanced look
(`replicates=3`, then `6`; `looks=[3,6]`). Use `whole`, `blocks`, `split`
(with `block`), then `holdout` (with the original `ref`).
For an unresolved comparison, change `replicates` to `6` and repeat `run`;
the first three replicates are reused.

```sh
uv run --project "$E" guidance-evals run whole.toml --project . --store "$S" --budget "$BUDGET"
uv run --project "$E" guidance-evals run blocks.toml --project . --store "$S" --budget "$BUDGET"
uv run --project "$E" guidance-evals run split.toml --project . --store "$S" --budget "$BUDGET"
uv run --project "$E" guidance-evals run holdout.toml --project . --store "$S" --budget "$BUDGET"
uv run --project "$E" guidance-evals analyze --project . --store "$S" --experiment NAME
uv run --project "$E" guidance-evals janitor --store "$S"
```

Repeat `run` to resume: complete trial IDs are skipped. After judge-only edits,
`analyze --project .` regrades saved artifacts without agent trials. Omit
`--project` to read existing grades offline. Execution changes need a new name.
`run --free` produces smoke-only evidence; `replicates=1, looks=[1]` is allowed
only with free/local models. Never delete guidance from a smoke report.

## Rules

- Verdicts use the production model; free or local models only smoke-test.
- Paid runs need a budget the user approved; pass it as `--budget`.
- Never select, tune or drop cases because arms did not differ.
- Never read holdout results while improving guidance.
- Loads and rule firings are diagnostics, never scores.
