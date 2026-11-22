---
name: council
description: >-
  Independent answers from the council models, anonymous cross-review, then a
  decision on the evidence. Run with /skill:council or from /implement.
disable-model-invocation: true
---

# Council

Goal: a decision backed by at least two independent answers, their anonymous
cross-reviews, and your own check of every claim it turns on.

The request is the skill's argument or the text a calling procedure supplies.
If empty, ask what the council should decide and stop.

You chair. Members: `council-opus`, `council-neon`, `council-sol`,
`council-argon`. Their files set model, thinking level and answer shape; never
set `model` or `effort` on their task items.

## 1. Answer

One `task` call, one item per member, task `Answer the request.` The shared
`context` is the brief: the request plus what members can't find alone
(decisions, constraints, paths, repo rules). Leave out your view. Say what the
answer must cover, not its wording: an exact phrase or one-line format makes
members drop their evidence.

- Retry a transient failure once; a member out of quota stays out.
- When the others are done and a member still runs after as long again as the
  slowest of them, stop it (`proc://<id>/kill`) and go on.
- Fewer than two answers: report the failure and stop.
- Use the returned agent IDs; omp renames duplicates.
- Send a running member nothing: its reply would replace its answer in
  `agent://<id>:raw`.

## 2. Review

Build the call in Python eval so reviewers get each answer byte for byte;
retyped answers lost content, and `read` without `:raw` cuts lines and names
the author.

```python
import random
BRIEF = "..."  # the stage-1 context
ids = {"council-opus": "...", "council-neon": "...", "council-sol": "...", "council-argon": "..."}  # members that answered → returned IDs
order = random.sample(list(ids), len(ids))
label = {m: "ABCD"[i] for i, m in enumerate(order)}
text = {m: read(f"agent://{ids[m]}:raw") for m in order}
tasks = []
for i, m in enumerate(order):
    others = [order[(i + k) % len(order)] for k in range(1, len(order))]
    body = "\n\n".join(f"## Answer {label[o]}\n\n{text[o]}" for o in others)
    tasks.append({"agent": m, "name": "Review" + m.split("-")[1].title(),
                  "task": "Review these answers.\n\n" + body,
                  "solutionSpace": "review of peer answers"})
print(label)
await tool.task({"context": BRIEF, "tasks": tasks})
```

Each reviewer sees only the others' answers, each answer once in every
position. Step 1's stop rule applies.

## 3. Decide

Reviews are evidence, not votes. Check each reported error against its answer
and verify any disagreement that would change the decision; without reviews,
verify the decisive claims yourself. Done when every deciding claim is verified
or reported as unverified.

## 4. Act

When the request calls for changes:

- **Obvious** (one correct change, settled by evidence, in scope): make it, or
  send it with `write agent://<id>` to the member whose answer covered it. One
  owner per file; verify the result.
- **Otherwise** (design choice, conflicting evidence, breaking,
  cross-repository or irreversible): `ask` with options and evidence, your
  recommendation preselected.

Commit only if the user asked.

## 5. Report

Answer in the requested format, then add only dissent that changed or
qualifies the decision, missing members or reviews, and changes made or
pending.
