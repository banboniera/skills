---
name: testing-guidance
description: Use to measure an omp skill, rule or command with trial runs, trigger tests or a benchmark.
---

# Testing guidance

Run the same realistic requests as headless omp sessions in throwaway copies
of a fixture, once per arm, and compare what the agents did. Arms: `without`
(the target removed), `with` (the working copy), `old=<git-rev>`. Every run is
a paid session; nothing paid starts without the user's approval.

```sh
T="$(realpath skill://testing-guidance/scripts/trial.py)"   # --help lists subcommands and flags
R="$(realpath skill://testing-guidance/scripts/report.py)"
```

1. **Eval set.** Write or extend `evals/<target-name>/evals.json` per
   [evals.md](evals.md) before any run. Done when every case the guidance
   handles has an eval that an agent without it would plausibly fail, plus
   trigger queries for a listed skill or a description-only rule.
2. **Free checks.** `hint` for a skill, `rules` for a triggered rule, and
   `run --dry-run --budget 0` (each arm loads only its own copy). To compare
   wordings of one passage, or to test a suspected no-op, use
   [micro-tests.md](micro-tests.md) first.
3. **Approval.** New guidance runs `without` and `with`; changed guidance runs
   `old=HEAD` and `with`, plus `without` to ask whether it is needed at all.
   Pilot with `run --limit 1 --reps 1 --budget 5`. Estimate: pilot cost per
   run × evals × arms × reps (default 3), plus trigger queries × reps × one
   short session. `ask` the user to approve the estimate, the model (the
   session default unless they name one) and the `--budget`.
4. **Run** in the background:

   ```sh
   python3 "$T" run --target <path> --evals <evals.json> \
     --out .workspaces/<name>/iteration-<N> --budget <USD> [--arm …] [--shadow-references]
   python3 "$T" triggers --target <path> --evals <evals.json> \
     --out .workspaces/<name>/iteration-<N> --split train --budget <USD>
   ```

   A run stops when the budget is spent, an arm's isolation fails, or a file
   outside the trial changes. Read the reason before rerunning.
5. **Grade** in a Python eval cell, then aggregate with
   `python3 "$R" <iteration dir> [--previous <iteration dir>]`:

   ```python
   from pathlib import Path
   exec(read("skill://testing-guidance/scripts/grade.py"))
   await grade(Path("<iteration dir>"), judge_batch, completion)
   ```

6. **Analyze** every flag in `benchmark.md` against the runs:
   - `with` loaded below 100%: fix the trigger first; content results mean
     little until the guidance loads.
   - `with` no better than `without`: the guidance is a no-op, or the evals
     miss its failure.
   - "same in every arm": the item does not discriminate, or the model does it
     anyway. "varies within an arm": more reps or a sharper item. "never
     passes": a wrong item, or guidance that does not reach the agent.
   - `eval_feedback.json` lists weak and missing expectations; fix the eval set
     for the next iteration.
   - Read the transcripts (`session/*.jsonl`) of failing and costly runs for
     steps the guidance wastes; code every run rewrote belongs in the skill's
     `scripts/`.

   With 3 reps, a difference within one standard deviation is noise.
7. **Review** the table and `report.html` with the user; `ask` for feedback
   where outputs need human judgment.
8. **Iterate.** Change the guidance per
   [writing-guidance](skill://writing-guidance), generalizing from the failures
   rather than fitting the prompts, and rerun into `iteration-<N+1>` with
   `--previous`. Stop when the user is satisfied, `with` passes what matters,
   or an iteration changes nothing. For a metric a script computes,
   [loop.md](loop.md) runs the loop unattended.

## Report

The verdict first: whether the guidance changes behavior, by how much (pass
and loaded rates per arm), and the money spent. Then the benchmark table, each
flag with its explanation, the changes per iteration, what stays unmeasured
(`question` rules, outputs only a person can judge, other models), and the
path to `report.html`.
