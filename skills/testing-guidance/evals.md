# Eval sets

`evals/<target-name>/evals.json` in the repository that owns the guidance,
fixtures beside it. Only `evals[].id` and `evals[].prompt` are required.
Working example: `evals/writing-guidance/evals.json` in the skills repository
(`realpath skill://testing-guidance` shows where it is).

```json
{
  "fixture": "fixture-shop",
  "setup": "ln -s ~/.cache/shop-deps/node_modules node_modules",
  "evals": [{
    "id": "rule-from-repeated-mistake",
    "prompt": "agents keep silencing type errors with `as any` in src/. make sure it stops",
    "baseline_prompt": "only for a command's without arm: the same request in plain words",
    "max_time": "15m",
    "expectations": ["The rule body tells the agent what to do instead of the cast"],
    "checks": [{"name": "a rule fires on as any", "run": "<shell command, exit 0 passes>"}]
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
  (`archive.prompts(query=...)` or `archive.search(...)` in a Python eval cell),
  with their paths and casual wording. One eval per case the guidance handles,
  including the case where the right move is to do nothing or ask.
- **Fixture:** copied into a fresh git repository under `/tmp` per run; without
  one the agent starts in an empty repository. `setup` runs in the copy first.
- **Checks** run in the copy after the agent finishes. Prefer them whenever a
  script can decide: tests pass, a file has the right content, a rule fires.
- **Expectations** are judged against the final answer, the diff and the check
  results, never knowing the arm. Write each so it passes only when the
  guidance did its job ("names the failing test and its input", not "mentions
  tests"), and write them before the first run.

## Triggers

For a listed skill or a description-only rule: 8–10 requests that should load
it (different phrasings, some never naming it, some where a neighboring skill
competes) and 8–10 near misses that share its words but need something else.
Only substantive requests: agents skip skills for one-step tasks. Mark about
40% `"split": "test"`: improve against `train`, judge on `test`.

## Rule cases

Offline cases for a triggered rule: `source` (`tool`, `text` or `thinking`),
`tool` and `path` for tool sources, `agent` for agent-scoped rules, and whether
it `fires`. Give every condition a near miss.

## Reading a run

`runs/<eval-id>/<arm>-<rep>/` holds `session/` (the full transcript),
`final.md`, `diff.patch` (the agent's changes), `checks.json`, `metrics.json`
(cost, tokens, tool calls, loaded skills and rules) and `grading.json`.
Guidance outside the target that links to it stays installed in every arm;
`run` names it, and `--shadow-references` hides such user rules in the
`without` arm.
