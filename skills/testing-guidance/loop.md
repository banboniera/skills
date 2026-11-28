# Unattended loop with /autoresearch

omp's `/autoresearch` edits, runs a harness, and keeps or reverts the edit by
a metric (`omp://autoresearch.md`). Use it when a script computes the metric:
trigger accuracy (`trial.py triggers`) or the `with` arm's check pass rate
(`trial.py run --arm with --split train`). Judged expectations need an eval
cell and stay in the manual loop.

The loop is bounded by two caps the user approves: `max_iterations` (at most
10) and the total `--budget`. Budget them for `max_iterations + 2` harness
runs: setup runs the harness once and the baseline once before the first
edit. The driving session's own cost is outside `--budget`: start it with
`omp --max-cost <USD>`.

1. Work in a dedicated worktree on an `autoresearch/*` branch: a discarded
   attempt runs `git reset --hard` and `git clean` on the tree.
   `git worktree add -b autoresearch/<name> ../<repo>-<name>`
   Record the shipped `HEAD` (`git rev-parse HEAD`) before the loop.
2. Write `autoresearch.sh` in the worktree root. It runs under plain `bash`,
   where `skill://` does not resolve: use the absolute path from
   `realpath skill://testing-guidance/scripts/trial.py`, and an `--out` under
   one fixed directory outside the worktree so every iteration shares one
   ledger. Only the train split runs here; the test split runs once at the
   end, so it stays held out.

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   cache="${XDG_CACHE_HOME:-$HOME/.cache}/omp-trials"
   python3 /abs/trial.py triggers --target skills/<name> --evals evals/<name>/evals.json \
     --out "$cache/<name>/loop-$(date +%s)" --split train --reps 3 --budget <approved total>
   ```

   It prints `METRIC trigger_accuracy_train=…` and exits 1 once the budget is
   spent.
3. In an omp session in the worktree, run `/autoresearch` with the goal. Pass
   `max_iterations` to every `init_experiment` call: a call without it removes
   the cap. Primary metric `trigger_accuracy_train` (higher), the target file
   as the only scope path, the eval set as off-limits.
4. Keep an attempt only when the metric rises.
5. The loop stops by itself at `max_iterations`. A run that exits 1 for the
   budget is logged as `crash`, which reverts only that unmeasured edit; the
   next turn is a resume: answer it with the report and call no tool.
6. Compare the candidate (`with`) to the shipped version (`old=HEAD`, or
   `old=<recorded rev>` if `HEAD` moved) on `--split test` once. For `triggers`,
   run one command per arm with distinct sibling output directories. Keep the
   shipped version unless the candidate wins on the approved metric. Report
   both held-out scores, the kept diff and total spend.
