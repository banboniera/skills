#!/usr/bin/env bash
# One drf-serializer-testing eval run: a fresh copy of a fixture, the skill installed per arm, a plain request, then grading.
# TASK: write (FIXTURE=shop|rental), review (weak tests in the shop app), change (rename an API field in the shop app).
#       ARM: new (this skill), none (no skill), asked (this skill, named in the request), old (the skill as committed at HEAD).
# Usage: run.sh <arm> <iteration> <n>   (TASK / FIXTURE / EVAL_MODEL / EVAL_THINKING optional). Run under bash.
set -euo pipefail
export NO_COLOR=1 FORCE_COLOR=0
arm=$1 iter=$2 n=$3
task=${TASK:-write}
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
skill="$repo/skills/drf-serializer-testing"
cache="$HOME/.cache/dst-eval"
python="$cache/venv/bin/python"
# Fixtures and graders run on their own Django and DRF, outside any project venv.
if [ ! -x "$python" ]; then
  UV_CACHE_DIR=/tmp/uv uv venv -q --python 3.14 "$cache/venv"
  UV_CACHE_DIR=/tmp/uv uv pip install -q --python "$python" "django==6.1.1" "djangorestframework==3.18.1"
fi

case $task in
  write) spec=${FIXTURE:-shop}; fixture=$spec; app=$( [ "$spec" = rental ] && echo rentals || echo orders )
         prompt="Write tests for the serializers in $app/serializers.py." ;;
  review) spec=review; fixture=shop
          prompt="Review the serializer tests in orders/tests/serializers/ and tell me what is wrong with them." ;;
  change) spec=change; fixture=change
          prompt="Rename the order API's discount_percent field to discount. Keep the database column as it is." ;;
esac

[ "$arm" = asked ] && prompt="Use the drf-serializer-testing skill. $prompt"

run="$repo/.workspaces/drf-serializer-testing/$task-$spec-$iter/$arm-$n"
ws="$cache/work/$task-$spec-$iter-$arm-$n-$(date +%s)/project"
mkdir -p "$run" "$(dirname "$ws")"
cp -r "$here/fixture-$fixture" "$ws"
sed -i "s|PYTHON|$python|" "$ws/AGENTS.md"
[ "$task" = review ] && cp "$here/review_tests.py" "$ws/orders/tests/serializers/test_serializers.py"

dest="$ws/.agents/skills/drf-serializer-testing"
case $arm in
  new | asked) mkdir -p "$dest" && cp -r "$skill/." "$dest" ;;
  old) mkdir -p "$ws/.agents/skills" && git -C "$repo" archive HEAD skills/drf-serializer-testing | tar -x -C "$ws/.agents" --exclude="*/evals" ;;
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
