---
description: Judge from first principles whether something is already the best possible solution, and propose a better one only when it really is better. Works for existing code and for things to build from scratch.
argument-hint: "<what to build, or what to rethink>"
---

# First principles

Work out the best possible solution from what is true about the problem: its
data, numbers, contracts, and the physics and math behind them. Ignore
convention, what similar systems do, and how long a change would take. Then
compare that with what exists. If what exists is already the best, say so.

Topic: $ARGUMENTS

If the topic is empty, ask what to build or rethink, and stop.

## 1. Learn the facts yourself

Read the code, docs, config, and tests the topic points at, and the callers of
that code. Work out from them the problem it solves, the volumes and limits, the
contracts others depend on, and why each nontrivial piece exists (a retry, a
lock, a sleep, a validation). Use `git log` and blame for pieces whose reason
isn't obvious. Measure or compute what you can instead of asking.

## 2. Ask only what you cannot settle

Ask a question only if all three hold:

- the code, docs, history, and request don't answer it;
- you can't make a guess you'd defend; and
- different answers would change your verdict or design.

Asking nothing is normal. Turn everything else into a stated assumption the
user can correct later. Don't ask checklist questions (non-goals, compliance,
growth plans) unless the verdict turns on them.

When you do ask, use one `ask` call: one form with a radio group per question,
or checkboxes when several answers can hold. Give concrete options (named
choices, or ranges for numbers), each saying how it changes the verdict.
Preselect your best guess; preselection marks it, so don't label it. Without
an `ask` tool, ask the same questions as a short numbered list with your
guesses.

Ask again later only when an answer raises another question that passes the
same test. If answers contradict each other under every reading, name the
conflict and ask which wins.

## 3. Derive the best solution

1. Ground truths. List the facts and constraints the solution must rest on,
   each with its source. A claim about a tool's capability or limit that
   decides a choice counts only once checked in its docs or source.
   Convention and the current design are assumptions until verified.
2. Floor. Where speed, cost, or size matters, compute what the fundamentals
   allow (events per second from daily volume, bytes over bandwidth) and
   compare with what exists or what is planned.
3. Prior art. Search docs and the web for how this exact problem is solved
   today. Note each finding with its link. Prior art supplies candidates and
   facts; it never justifies a choice by itself.
4. Candidates. Derive the genuinely different designs the facts allow,
   including what exists. Pick the best against the facts: the one that meets
   every requirement with the fewest parts. Running cost counts; migration
   effort does not. Never hand-roll crypto, auth, or date and time handling.
5. Impossible requirements, such as exactly-once delivery over a network or
   100% uptime: mark them unmet, say why, and offer the strongest achievable
   guarantee as a relaxation for the user to accept.

## 4. Decide the verdict

Compare the best design with what exists. Each difference counts only if it
names the fact that makes it better and the concrete gain: a requirement it
meets that the current one fails, a number it improves, or parts and failure
modes it removes. Drop differences that rest on taste, novelty, convention, or
"more scalable" or "more flexible" without a stated need.

- **Already the best:** no difference survives. Say so plainly and show why:
  the facts, the floor, and the alternatives you checked and why each loses.
  Propose nothing.
- **Better exists:** propose only the surviving differences.
- **Nothing exists yet:** propose the design.

Before reporting, give a fresh subagent the topic, the ground truths, and your
verdict, but not your reasoning. Ask it to attack the verdict: a better design
you missed, or a proposed change whose gain is not real. Fix what holds; record
the rest with why it fails. Without a subagent tool, do this pass yourself as a
separate step.

## Report

Already the best:

```
**Verdict: already the best solution.** <one-line reason>

## Why
- <fact or floor>: <how the current solution meets it>
- Checked <alternative>: loses because <...>
- Assumed: <...> (would change the verdict if <...>)
```

Better exists, or nothing exists yet:

```
**Verdict:** <better solution exists | new design>. <the change, briefly>

## Ground truths
- Fact: <...> (source)
- Constraint: <...> (source)
- Assumed: <...>
- Unmet: <requirement> (why; proposed relaxation)

## Proposed solution
<what changes or what to build: components, data, key flows; enough to build from>

## Why it is better
- <change>: <fact it rests on> → <concrete gain>
- Rejected <alternative>: <why it loses>
- Red team: <objection>: fixed, or rejected because <...>

## What would prove it wrong
<cheapest experiment and the result that would change the verdict>
```

No migration plan, timeline, or effort estimate unless asked.

## After a proposal

1. Save the proposal to `docs/first-principles/YYYY-MM-DD-<topic>.md` in the
   repository root, or ask where to save it when there is no repository.
   Don't commit it.
2. Ask with `ask` whether to approve it: one radio group with "Approve"
   (preselected) and "Change something", and a text field for the changes.
   Apply changes to both the reply and the file. Only a submitted "Approve"
   counts: cancellation, a result that says the form timed out, or no answer
   leaves it unapproved.
3. Once approved, read `skill://writing-plans` and follow it with the file
   path. If that skill is unavailable, say so and ask how to proceed. Don't
   implement before a plan exists.
