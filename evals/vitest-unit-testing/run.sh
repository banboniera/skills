#!/usr/bin/env bash
# One vitest-unit-testing eval run: a fresh copy of a fixture, the skill installed per arm, a plain request, then grading.
# TASK: write (FIXTURE=billing|tasks), review (weak tests for the billing fixture), change (optional due date).
#       ARM: new (this skill), none (no skill), asked (this skill, named in the request), old (the skill before the rewrite, commit e23f171).
#       ref (antfu vitest API skill only, from REF_SKILL), refasked (ref, named in the request), both (this skill and ref).
# Usage: run.sh <arm> <iteration> <n>   (TASK / FIXTURE / EVAL_MODEL / EVAL_THINKING optional). Run under bash.
set -euo pipefail
export NO_COLOR=1 FORCE_COLOR=0
arm=$1 iter=$2 n=$3
task=${TASK:-write}
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
skill="$repo/skills/vitest-unit-testing"
ref_skill=${REF_SKILL:-$HOME/Documents/HuggingCar/frontend/.agents/skills/vitest}
cache="$HOME/.cache/vitest-eval"
# Fixtures run on their own test stack, outside any project.
if [ ! -d "$cache/deps/node_modules/vitest" ]; then
  mkdir -p "$cache/deps" && cp "$here/fixture-billing/package.json" "$cache/deps/package.json"
  (cd "$cache/deps" && BUN_TMPDIR=/tmp/bun bun install --silent)
fi

case $task in
  write) spec=${FIXTURE:-billing}; fixture=$spec
         if [ "$spec" = tasks ]; then
           prompt="Write unit tests for src/utils/dueLabel.ts, src/hooks/useAutosave.ts, and src/components/TaskList.tsx."
         else
           prompt="Write unit tests for src/utils/money.ts, src/hooks/useDebouncedValue.ts, src/store/api.ts, and src/components/InvoiceForm.tsx."
         fi ;;
  review) spec=review; fixture=billing
          prompt="Review the unit tests in src/ and tell me what is wrong with them." ;;
  change) spec=change; fixture=change
          prompt="The due date on invoices is now optional: the invoice form should accept a blank due date and send it as due_date: null. Make that change." ;;
esac

[ "$arm" = asked ] && prompt="Use the vitest-unit-testing skill. $prompt"
[ "$arm" = refasked ] && prompt="Use the vitest skill. $prompt"

run="$repo/.workspaces/vitest-unit-testing/$task-$spec-$iter/$arm-$n"
ws="$cache/work/$task-$spec-$iter-$arm-$n-$(date +%s)/project"
mkdir -p "$run" "$(dirname "$ws")"
cp -r "$here/fixture-$fixture" "$ws"
ln -sfn "$cache/deps/node_modules" "$ws/node_modules"
[ "$task" = review ] && cp -r "$here/review/src/." "$ws/src/"

dest="$ws/.agents/skills/vitest-unit-testing"
case $arm in
  new | asked) mkdir -p "$dest" && cp -r "$skill/." "$dest" ;;
  old) mkdir -p "$ws/.agents/skills" && git -C "$repo" archive e23f171 skills/vitest-unit-testing | tar -x -C "$ws/.agents" ;;
  ref | refasked) mkdir -p "$ws/.agents/skills/vitest" && cp -r "$ref_skill/." "$ws/.agents/skills/vitest" ;;
  both) mkdir -p "$dest" "$ws/.agents/skills/vitest" && cp -r "$skill/." "$dest" && cp -r "$ref_skill/." "$ws/.agents/skills/vitest" ;;
  none) ;;
esac
(cd "$ws" && git init -q && git add -A && git -c user.email=e@x -c user.name=e commit -qm fixture)
echo "$ws" >"$run/workspace"

pin=()
overlay="$here/overlay.yml"
if [ -n "${EVAL_MODEL:-}" ]; then pin=(--model "$EVAL_MODEL"); overlay="$here/overlay-pinned.yml"; fi
[ -n "${EVAL_THINKING:-}" ] && pin+=(--thinking "$EVAL_THINKING")
start=$(date +%s)
set +e
omp -p --no-session --no-title --approval-mode yolo --max-time 40m "${pin[@]}" --config "$overlay" --cwd "$ws" --mode json \
  "$prompt" >"$run/events.jsonl" 2>"$run/stderr.txt" </dev/null
echo $? >"$run/exit_code"
set -e
echo "{\"total_duration_seconds\": $(($(date +%s) - start))}" >"$run/timing.json"
python3 "$here/extract.py" "$run"
if [ "$task" = review ]; then
  python3 "$here/grade_review.py" "$run" "$ws"
else
  python3 "$here/grade.py" "$run" "$ws" "$spec"
fi
