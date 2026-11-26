---
name: council
description: >-
  Independent answers from the council models, anonymous cross-review, then a
  decision on the evidence. Run with /skill:council or from /implement.
disable-model-invocation: true
---

# Council

Goal: a decision backed by at least two independent answers to the same brief,
their anonymous cross-reviews, and your own check of every claim it turns on.

The request is the skill's argument or the text a calling procedure supplies.
If empty, ask what the council should decide and stop.

You chair. Members: `council-opus`, `council-neon`, `council-sol`,
`council-astra`, `council-argon`. Their agent files set model, thinking level
and answer shape; never set `model` or `effort` on their task items.

Write the brief, every `ask` and the report in the repository's names (tables,
columns, routes) and the user's words. Before sending a report or `ask`, find
each term that is neither (members bring them from researched products: driver,
fleet manager, whole account, principal) and replace it with the repository
name, or write that name beside it.

## 1. Answer

The brief is the shared `context` of the member tasks: the request, what
members can't find alone (the user's decisions, constraints, paths, repo
rules), and what the answer must cover.

- Leave out your view.
- Name no sources, products or alternatives for members to consider, not even
  as examples: members choose their own research, and any list you give
  narrows it.
- Say what the answer must cover, not its wording: an exact phrase or one-line
  format makes members drop their evidence.

Spawn one `task` call, one item per member, task `Answer the request.` Keep the
returned agent IDs; omp renames duplicates.

- **Failures:** respawn a transient failure once. Write a member stopped by its
  request budget once: `Write your final answer now from what you have.` A
  member out of quota, or failing twice, stays out.
- **Stop:** when the others are done and a member still runs after as long
  again as the slowest of them, stop it (`proc://<id>/kill`) and go on.
- **Messages:** until the reviews are in, send members only a change the user
  makes to the request. A running member gets it ending "Your final message
  still holds the whole answer." A finished member is rerun with the changed
  brief instead, because a reply to a message would replace its answer in
  `agent://<id>:raw`. Never ask a running member to hurry or wrap up; the stop
  rule decides.
- **Quorum:** fewer than two answers to the current brief: report the failure
  and stop.

## 2. Review

Run it whenever two or more answers came back, also when they agree or a
member failed. Build the call in Python eval so reviewers get each answer byte
for byte; retyped answers lost content, and `read` without `:raw` cuts lines
and names the author.

```python
import random
BRIEF = "..."  # the brief the answers were written to, with any change from the user
ids = {"council-opus": "...", "council-neon": "...", "council-sol": "...", "council-astra": "...", "council-argon": "..."}  # members that answered → returned IDs
order = random.sample(list(ids), len(ids))
label = {m: "ABCDE"[i] for i, m in enumerate(order)}
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
position. The failure and stop rules of step 1 apply. When the user changes
the request during review, a change that alters what the answers must cover
sends the council back to step 1 with the changed brief, so no review mixes
answers to two briefs; a change only to what reviewers should check goes to
the running reviewers under step 1's message rule.

## 3. Decide

Reviews are evidence, not votes. Check each reported error against its answer,
and verify every disagreement that would change the decision; if every review
failed, verify the decisive claims yourself. Done when every deciding claim is
verified or reported as unverified.

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

Answer in the requested format. Each recommendation first says what goes wrong
in this product today, then its evidence. Then add only dissent that changed
or qualifies the decision, missing members or reviews, and changes made or
pending.
