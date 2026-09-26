#!/usr/bin/env bash
# One django-model-testing eval run: a fresh copy of a fixture, the skill installed per arm, a plain request, then grading.
# TASK: write (FIXTURE=garage|clinic), review (weak tests in the garage app), change (raise a limit in the clinic app),
#       migrate (test a data migration). ARM: new (this skill), none (no skill),
#       asked (this skill, named in the request), old (the skill as committed at HEAD).
# Usage: run.sh <arm> <iteration> <n>   (TASK / FIXTURE / EVAL_MODEL / EVAL_THINKING optional). Run under bash.
set -euo pipefail
export NO_COLOR=1 FORCE_COLOR=0
arm=$1 iter=$2 n=$3
task=${TASK:-write}
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
skill="$repo/skills/django-model-testing"
cache="$HOME/.cache/dmt-eval"
python="$cache/venv/bin/python"
# Fixtures and graders run on their own Django, outside any project venv.
if [ ! -x "$python" ]; then
  UV_CACHE_DIR=/tmp/uv uv venv -q --python 3.14 "$cache/venv"
  UV_CACHE_DIR=/tmp/uv uv pip install -q --python "$python" "django==6.1.1"
fi

case $task in
  write) spec=${FIXTURE:-garage}; fixture=$spec; app=$( [ "$spec" = clinic ] && echo clinic || echo shop )
         prompt="Write tests for the models in $app/models.py." ;;
  review) spec=review; fixture=garage
          prompt="Review the model tests in shop/tests/ and tell me what is wrong with them." ;;
  change) spec=change; fixture=change
          prompt="Appointments may now last up to 180 minutes instead of 120. Make that change." ;;
  migrate) spec=migrate; fixture=migrate
           prompt="Write tests for the data migration crm/migrations/0003_backfill_phone_digits.py." ;;
esac
[ "$arm" = asked ] && prompt="Use the django-model-testing skill. $prompt"

run="$repo/.workspaces/django-model-testing/$task-$spec-$iter/$arm-$n"
ws="$cache/work/$task-$spec-$iter-$arm-$n-$(date +%s)/project"
mkdir -p "$run" "$(dirname "$ws")"
cp -r "$here/fixture-$fixture" "$ws"
sed -i "s|PYTHON|$python|" "$ws/AGENTS.md"
[ "$task" = review ] && cp "$here/review_tests.py" "$ws/shop/tests/test_models.py"

dest="$ws/.agents/skills/django-model-testing"
case $arm in
  new | asked) mkdir -p "$dest" && cp -r "$skill/." "$dest" ;;
  old) mkdir -p "$ws/.agents/skills" && git -C "$repo" archive HEAD skills/django-model-testing | tar -x -C "$ws/.agents" --exclude="*/evals" ;;
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
