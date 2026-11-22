# Unattended loop with /autoresearch

omp's `/autoresearch` edits, runs a harness, and keeps or reverts the edit by
a metric. Use it when a script computes the metric: trigger accuracy
(`trial.py triggers`) or the `with` arm's check pass rate (`trial.py run --arm
with`). Judged expectations need an eval cell and stay in the manual loop.
Each iteration is a paid benchmark: get approval for `max_iterations` × the
cost of one iteration.

1. Work in a dedicated worktree on an `autoresearch/*` branch, because a
   discarded attempt runs `git reset --hard` and `git clean` on the tree:
   `git worktree add -b autoresearch/<name> ../<repo>-<name>`.
2. Write `autoresearch.sh` in the worktree root. It runs under plain `bash`,
   where `skill://` does not resolve, so use the absolute path from
   `realpath skill://testing-guidance/scripts/trial.py`, and an `--out` outside
   the worktree:

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   OUT=/tmp/<name>-loop/$(date +%s)
   for split in train test; do
     python3 /abs/trial.py triggers --target skills/<name> --evals evals/<name>/evals.json \
       --out "$OUT" --split "$split" --reps 3 --budget 5
   done
   ```

   `trial.py` prints `METRIC trigger_accuracy_<split>=…` (`run` prints
   `METRIC checks_<arm>=…`).
3. In an omp session in the worktree, run `/autoresearch` with the goal; set
   the primary metric `trigger_accuracy_train` (higher), `max_iterations`, the
   target file as the only scope path and the eval set as off-limits.
4. Keep an attempt only when train rises and test does not fall. The user
   reviews the kept diff and merges it by hand.
