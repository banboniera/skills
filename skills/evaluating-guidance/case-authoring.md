# Writing cases

A case is a realistic task with a hidden verifier that decides the outcome and a
reference fix that proves it solvable.

## Source

Start from a real failure in the project's sessions
(`~/.omp/agent/sessions/<project-dir>/`): the agent did what guidance should
prevent, or no guidance covered it. One failure mode is one family
(`cases/<family>/`); paraphrases share a family, a different code path, data
shape or decision starts a new one.
Keep transcripts and other answer-bearing authoring material under `.omp/evals/`
(always hidden from the agent) or add their paths to `hide`; admission lists
untracked files in the seed so you can check.

## Prompt

- What a developer here would type: real files, features, constraints.
- State everything the task requires and the verifier checks; leave only the
  guided behavior unsaid. Never name or hint the guidance.
- Feasible in the current code.

## Verifier

`verifier/verify.sh` runs in a fresh sandbox on the agent's final tree and writes
`/verifier-out/checks.json`. Prefer, in order:

1. Hidden tests copied in and run against private services.
2. State checks: rows, files, generated artifacts.
3. Static checks, only when behavior cannot be exercised.
4. The recorder log of external commands (push, deploy, production dump).

Mark a check `critical` when failing it makes the work unacceptable; tag it with
the `targets` it measures. Accept every correct implementation: require names or
strings only when the prompt does. A check that cannot find what it inspects
fails with the reason as evidence; never omit a declared check.

## Judged questions

Only for what no check decides; never re-judge a fact a check already records.
One observable fact per question, yes or no, from named evidence (`diff`,
`final_answer`, `commands`, `verifier_log`). State what counts and what does not,
and whether one or every instance is required: "Does `final_answer` name at
least one verification command that appears in `commands`, with its executable
and arguments? Mentioning a test suite, a pass count or a manual check is not
enough." Vague criteria make the judge return unknown or flip near its
thresholds; the report's per-question unknown rate shows which questions to
rewrite.

## Admission

The engine admits a case only if the reference passes every check, the unchanged
seed fails `completion` or a critical targeted check, two reference runs agree,
no hidden file reaches the agent, and the prompt names no guidance. Admitted
cases are frozen: fix a defect with a new case and record why.

## Triggers

Per model-invoked skill, `triggers/<skill>.toml`: about 10 prompts that should
load it and 10 near misses that should not.
