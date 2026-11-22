---
description: >-
  Get independent answers from the council models, have them review each other
  anonymously, then decide and act on the evidence.
argument-hint: "<question or task>"
---

# Council

Request: $ARGUMENTS

If the request is empty, ask what the council should decide and stop.

You chair the council. Its members are the agents `council-opus`,
`council-neon`, `council-sol` and `council-argon`. Their files pin model and thinking level, so
never set `model` or `effort` on their task items.

## 1. Answer

Make one `task` call with one item per member and the task
`Answer the request.` The shared `context` is the brief: the request plus what
members cannot discover alone (conversation decisions, constraints, paths,
repository rules). Leave out your own view so members do not anchor on it.

Retry a failed member once. With fewer than two answers, report the failure and
stop. Use the agent IDs the call returns; omp renames duplicate names. Send a
member nothing while it answers: its reply to you becomes its latest output,
and `agent://<id>:raw` then returns that reply instead of the answer.

## 2. Review

Build the review call in Python eval, so reviewers get each answer byte for
byte; retyped answers lost content in testing. Without `:raw`, `read` cuts long
lines and its notice names the author.

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

Each reviewer gets only the other answers, and each answer appears once in
every position.

## 3. Decide

Reviews are evidence, not votes. Check each reported error against the original
answer, and verify yourself any disagreement that would change the decision. If
reviews are missing, verify the decisive claims yourself.

## 4. Act

When the request calls for changes:

- **Obvious** (one correct change, settled by evidence, within the request):
  make it, or send it with `write agent://<id>` to the member whose answer
  covered it, since that agent keeps its context. One owner per file; verify
  the result.
- **Otherwise** (a product or design choice, conflicting evidence, a breaking,
  cross-repository or irreversible change): use `ask` with the options, their
  evidence and your recommendation first.

Never commit unless the user asked.

## 5. Report

Answer in the format the request asks for. Then add only what the user needs:
dissent that changed or qualifies the decision, missing members or reviews, and
changes made or awaiting the user. Omit agreement and settled side points.
