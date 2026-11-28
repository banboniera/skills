---
name: testing-guidance
description: Use to measure an omp skill, rule or command with trial runs, trigger tests or a benchmark.
---

# Testing guidance

The goal is a verdict backed by runs: does this guidance make agents do the
right thing more often than without it, and does it load when it should, for
no more money than the user approved. Each eval request runs as a headless omp
session in a throwaway copy of its fixture, once per arm: `without` (the
target removed), `with` (the working copy) or `old=<git-rev>`.

```sh
T="$(realpath skill://testing-guidance/scripts/trial.py)"   # --help lists subcommands and flags
R="$(realpath skill://testing-guidance/scripts/report.py)"
```

1. **Eval set.** Write or extend `evals/<target-name>/evals.json` per
   [evals.md](evals.md): one eval for each case the guidance handles, which
   an agent without it could plausibly fail, plus trigger queries for a listed
   skill or a description-only rule. Write the goal as numbers the benchmark
   reports, for example "`with` loads the skill in every run, passes ≥ 80% of
   checks and expectations, and beats `without`; trigger accuracy ≥ 85% on
   the test split".
2. **Validate, then dry-run.** Use `hint` for a skill or `rules` for a
   triggered rule. Then use `run --dry-run --budget 0` on the planned arms;
   fix any isolation error before a paid pilot.
3. **Approval.** New guidance runs `without` and `with`; changed guidance runs
   `old=HEAD` and `with`, plus `without` when the question is whether it is
   needed at all. Count the sessions of one iteration (evals × arms × reps,
   default 3, plus trigger queries × reps) and ask the user to approve, in one
   question: the eval prompts and expectations, the goal, the model (the
   session default unless they name one), the number of iterations (default
   3) and one total budget. Wording micro-tests ([micro-tests.md](micro-tests.md))
   cost cents and need the same approval.
4. **Pilot, then run.** Start with `run --limit 1 --reps 1` and compare its
   cost per session with your estimate. If the plan still fits, run in the
   background with `--budget <approved total>`; otherwise ask again. All
   iterations sharing an output parent use its `spend.jsonl`; after another
   approval pass the old total plus the new amount. Keep output outside the
   guarded trees.

   ```sh
   cache="${XDG_CACHE_HOME:-$HOME/.cache}/omp-trials"
   python3 "$T" run --target <path> --evals <evals.json> \
     --out "$cache/<name>/iteration-<N>" --split train --budget <USD> [--arm …] [--hide-references]
   python3 "$T" triggers --target <path> --evals <evals.json> \
     --out "$cache/<name>/iteration-<N>" --split train --budget <USD>
   ```

   A run exits 1 when the budget is spent or reserved, an arm loads the wrong
   copy, or a file outside the trial changes; fix the cause before rerunning.
5. **Grade** in a Python eval cell (judge calls, a few cents, outside the
   ledger), then aggregate with `python3 "$R" <iteration dir> [--previous <dir>]`:

   ```python
   from pathlib import Path
   exec(read("skill://testing-guidance/scripts/grade.py"))
   await grade(Path("<iteration dir>"), judge_batch, completion)
   ```

6. **Analyze** every flag in `benchmark.md` against the runs:
   - `with` loads below 100%: fix the trigger first; content results mean
     little until the guidance loads.
   - A trigger miss prints the skills loaded in order: a near miss that loads
     the target only after a skill that links to it routed correctly.
   - `without` touched the target's files: the baseline leaked; rerun with
     `--hide-references` or read those runs as contaminated.
   - `with` no better than `without`: the guidance is a no-op, or the evals
     miss its failure.
   - "same in every arm", "never passes", "varies within an arm": the item
     does not separate the arms, cannot pass, or needs more reps.
   - `eval_feedback.json` lists weak and missing expectations: fix the eval
     set before the next iteration, and rerun the previous version on it as
     `old=<rev>` instead of comparing with older numbers.
   - Read the transcripts (`session/*.jsonl`) of failing and costly runs for
     steps the guidance wastes; code every run rewrote belongs in `scripts/`.
7. **Iterate or stop.** When the request is to check or measure, stop here:
   the guidance stays as it is, and the report proposes the changes. When it
   is to improve the guidance, stop once the goal is met, the budget is spent,
   the approved iterations have run, or the last change did not raise the goal
   metric; otherwise change the guidance per
   [writing-guidance](skill://writing-guidance), generalizing from the
   failures instead of fitting the prompts, and run the next iteration from
   step 4. Evaluate the candidate against the shipped version on `test`
   once; keep the shipped version unless the candidate wins. For a scripted
   metric, [loop.md](loop.md) runs the train loop unattended.

## Report

The verdict first: goal met or not, how the arms differ (loaded, pass rates),
the money spent of the budget, and why the iterations stopped. Then the
benchmark table, each flag with its explanation, the changes per iteration,
what stays unmeasured (rule judges, outputs only a person can judge, other
models), and the path to `report.html`.
