#!/usr/bin/env bash
# One playwright-e2e-testing eval run: a fresh copy of a fixture, the skill installed per arm, a plain request, then grading.
# TASK: write (FIXTURE=workshop|rooms), review (weak spec for the workshop orders page), change (search by customer too).
#       ARM: new (this skill), none (no skill), asked (this skill, named in the request), old (the skill before the rewrite, commit 0c2bfc4).
# Usage: run.sh <arm> <iteration> <n>   (TASK / FIXTURE / EVAL_MODEL / EVAL_THINKING optional). Run under bash.
set -euo pipefail
export NO_COLOR=1 FORCE_COLOR=0
arm=$1 iter=$2 n=$3
task=${TASK:-write}
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
skill="$repo/skills/playwright-e2e-testing"
cache="$HOME/.cache/pw-eval"
# Fixtures run on their own Playwright, outside any project (browsers come from the shared Playwright cache).
if [ ! -d "$cache/deps/node_modules/@playwright/test" ]; then
  mkdir -p "$cache/deps" && cp "$here/fixture-workshop/package.json" "$cache/deps/package.json"
  (cd "$cache/deps" && BUN_TMPDIR=/tmp/bun bun install --silent && npx playwright install chromium)
fi

case $task in
  write) spec=${FIXTURE:-workshop}; fixture=$spec
         page=$( [ "$spec" = rooms ] && echo bookings || echo orders )
         prompt="Write e2e tests for the $page page." ;;
  review) spec=review; fixture=workshop
          prompt="Review the e2e spec e2e/orders.spec.ts and tell me what is wrong with it." ;;
  change) spec=change; fixture=change
          prompt="Search on the orders page should find orders by customer name as well as by plate. The backend now takes \`search\` instead of \`plate\` and matches both case-insensitively, so send the text as typed (trimmed) and label the box \"Search orders\". Make that change." ;;
esac

[ "$arm" = asked ] && prompt="Use the playwright-e2e-testing skill. $prompt"

run="$repo/.workspaces/playwright-e2e-testing/$task-$spec-$iter/$arm-$n"
ws="$cache/work/$task-$spec-$iter-$arm-$n-$(date +%s)/project"
mkdir -p "$run" "$(dirname "$ws")"
cp -r "$here/fixture-$fixture" "$ws"
ln -sfn "$cache/deps/node_modules" "$ws/node_modules"
port=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
sed -i "s/__PORT__/$port/g" "$ws/playwright.config.ts"
[ "$task" = review ] && cp "$here/review_spec.ts" "$ws/e2e/orders.spec.ts"

dest="$ws/.agents/skills/playwright-e2e-testing"
case $arm in
  new | asked) mkdir -p "$dest" && cp -r "$skill/." "$dest" ;;
  old) mkdir -p "$ws/.agents/skills" && git -C "$repo" archive 0c2bfc4 skills/playwright-e2e-testing | tar -x -C "$ws/.agents" ;;
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
