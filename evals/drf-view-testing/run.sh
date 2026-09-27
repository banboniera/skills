#!/usr/bin/env bash
# One drf-view-testing eval run: a fresh copy of a fixture, the skill installed per arm, a plain request, then grading.
# TASK: write (FIXTURE=helpdesk|docs), review (weak tests in the helpdesk app), change (let viewers create tickets).
#       ARM: new (this skill), none (no skill), asked (this skill, named in the request), old (the skill as committed at HEAD).
# Usage: run.sh <arm> <iteration> <n>   (TASK / FIXTURE / EVAL_MODEL / EVAL_THINKING optional). Run under bash.
set -euo pipefail
export NO_COLOR=1 FORCE_COLOR=0
arm=$1 iter=$2 n=$3
task=${TASK:-write}
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
skill="$repo/skills/drf-view-testing"
cache="$HOME/.cache/dst-eval"
python="$cache/venv/bin/python"
# Fixtures and graders run on their own Django and DRF, outside any project venv (shared with drf-serializer-testing).
if [ ! -x "$python" ]; then
  UV_CACHE_DIR=/tmp/uv uv venv -q --python 3.14 "$cache/venv"
  UV_CACHE_DIR=/tmp/uv uv pip install -q --python "$python" "django==6.1.1" "djangorestframework==3.18.1"
fi

case $task in
  write) spec=${FIXTURE:-helpdesk}; fixture=$spec; app=$( [ "$spec" = docs ] && echo documents || echo tickets )
         prompt="Write tests for the views in $app/views.py." ;;
  review) spec=review; fixture=helpdesk
          prompt="Review the view tests in tickets/tests/views/ and tell me what is wrong with them." ;;
  change) spec=change; fixture=change
          prompt="Viewers may now create tickets, but they still cannot edit, close, or delete them. Make that change." ;;
esac

[ "$arm" = asked ] && prompt="Use the drf-view-testing skill. $prompt"

run="$repo/.workspaces/drf-view-testing/$task-$spec-$iter/$arm-$n"
ws="$cache/work/$task-$spec-$iter-$arm-$n-$(date +%s)/project"
mkdir -p "$run" "$(dirname "$ws")"
cp -r "$here/fixture-$fixture" "$ws"
sed -i "s|PYTHON|$python|" "$ws/AGENTS.md"
[ "$task" = review ] && cp "$here/review_tests.py" "$ws/tickets/tests/views/test_views.py"

dest="$ws/.agents/skills/drf-view-testing"
case $arm in
  new | asked) mkdir -p "$dest" && cp -r "$skill/." "$dest" ;;
  old) mkdir -p "$ws/.agents/skills" && git -C "$repo" archive HEAD skills/drf-view-testing | tar -x -C "$ws/.agents" --exclude="*/evals" ;;
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
"$python" "$here/extract.py" "$run"
if [ "$task" = review ]; then
  "$python" "$here/grade_review.py" "$run" "$ws"
else
  "$python" "$here/grade.py" "$run" "$ws" "$spec" "$python"
fi
