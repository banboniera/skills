# Eval sets

`evals/<target-name>/evals.json` in the repository that owns the guidance.
Only `evals[].id` and `evals[].prompt` are required. Working examples:
`evals/writing-guidance/evals.json` and `evals/testing-guidance/evals.json`
next to the skills directory (`realpath skill://testing-guidance` shows where).

```json
{
  "fixture": "fixture-shop",
  "evals": [{
    "id": "mistake-an-existing-rule-covers",
    "repo": "~/Documents/HuggingCar/api", "rev": "575c1429",
    "prompt": "agents keep calling .set() on relations in serializers. make it stop",
    "baseline_prompt": "only for a command's without arm: the same request in plain words",
    "max_time": "15m",
    "expectations": ["Finds the existing rule and adds no second one for the same mistake"],
    "checks": [{"name": "one rule covers .set()", "run": "<shell command in the copy; exit 0 passes>"}]
  }],
  "triggers": [
    {"query": "agents keep adding eslint-disable comments, make them stop", "should_trigger": true},
    {"query": "fix the type error in src/cart.ts", "should_trigger": false, "split": "test"}
  ],
  "rule_cases": [
    {"snippet": "const v = raw as any", "source": "tool", "tool": "edit", "path": "src/a.ts", "fires": true},
    {"snippet": "you can use any of them", "source": "text", "fires": false}
  ]
}
```

## Evals

- **Prompts** read like real requests: take them from the user's sessions
  (`archive.prompts(query=...)` or `archive.search(...)` in a Python eval
  cell), with their paths and casual wording. One eval per case the guidance
  handles, including the case where the right move is to change nothing,
  reuse what exists, or ask.
- **Discipline guidance** (rules the agent knows and skips) needs prompts with
  pressure: a deadline, sunk work, an explicit request for the shortcut.
  Without it both arms comply and the eval measures nothing.
- **Fixture:** a directory beside the eval set, or `repo` (and `rev`, default
  `HEAD`) for a real repository on this machine: its tracked files at that
  revision, so untracked secrets and build output stay out. Pin `rev` so
  reruns compare the same code. `setup` runs in the copy first; without a
  fixture the agent starts in an empty repository.
- **Checks** run in the copy after the agent finishes. Prefer them whenever a
  script can decide: tests pass, a file has the right content, a rule fires.
- **Expectations** are judged against the final answer, the diff and the check
  results, with the target's name masked and the arm hidden. Each passes only
  when the guidance did its job ("names the failing test and its input", not
  "mentions tests").

## Triggers

For a listed skill or a description-only rule: 8–10 requests that should load
it (different phrasings, some never naming it, some where a neighboring skill
competes) and 8–10 near misses that share its words but need something else.
Only substantive requests: agents skip skills for one-step tasks. Mark about
40% `"split": "test"`, positives and negatives alike; improve against `train`,
judge on `test` once at the end.

## Rule cases

Offline cases for a triggered rule: `source` (`tool`, `text` or `thinking`),
`tool` and `path` for tool sources, `agent` for agent-scoped rules, and
whether it `fires`. Give every condition a near miss.

## Reading a run

`runs/<eval-id>/<arm>-<rep>/` holds `session/` (the full transcript),
`final.md`, `diff.patch`, `checks.json`, `metrics.json` and `grading.json`.
Every arm runs with memory, session history (`archive`), model fallback,
computer use, the advisor and the user's MCP servers off. Guidance that links
to the target stays installed in every arm unless `--hide-references` hides it
in `without`. A `without` agent can still find the target on disk; "touched
files" in the benchmark counts those runs.
