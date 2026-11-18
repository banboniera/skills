---
description:
  Ask a council of three models (Opus medium, Astra medium, Sol high) to answer
  independently and review each other anonymously, then chair the result and
  act on it.
argument-hint: "<question or task for the council>"
---

# Council

Convene the council on: $ARGUMENTS

If that is empty, ask the user what the council should decide and stop.

You are the chairman. The members are the task agents `council-opus`,
`council-astra` and `council-sol`; each agent file pins its model and thinking
level. Never pass `effort` or `model` on their task items: either overrides
that pinning or fails preflight.

## 1. Brief

Write the shared `context` once: the user's request verbatim, plus the facts a
member cannot discover alone (relevant conversation decisions, constraints,
paths, the repository and its rules that apply). Do not include your own
answer, leaning or hypothesis: members must not anchor on the chairman.

## 2. Answer independently

One `task` call with three items, one per member, named `CouncilOpus`,
`CouncilAstra` and `CouncilSol`. Each item asks for:

- the answer or recommendation, with the evidence behind each claim;
- alternatives considered and why they lose;
- confidence (high, medium or low) and what evidence would change the answer.

Members inspect and research only in this stage. Wait for all three. Retry a
failed member once; if it fails again, continue with the remaining members
and report the gap. Fewer than two answers is no council: report what failed
and stop.

## 3. Review anonymously

Label the answers `Answer A`, `Answer B`, `Answer C` in an order you choose at
random, and remove model names and self-references from their text. Then make
one `task` call with one review item per member, named `ReviewOpus`,
`ReviewAstra` and `ReviewSol`, using the same agent as that member. Each
reviewer receives only the answers it did not write, in a different order for
each reviewer, and is asked:

- for each answer: errors (verified, with evidence), gaps and strengths;
- which claims it checked itself and the result;
- a ranking, best first, with the deciding reason.

Answers from a member that failed in stage 2 are not reviewed.

## 4. Chair

Settle the outcome yourself. Rankings are evidence, not votes: a verified
error outweighs any majority, and an unverified disagreement that matters
gets checked by you before you decide. Report to the user:

1. **Decision**: the council's answer or recommendation.
2. **Consensus**: what all members agreed on.
3. **Dissent**: disagreements, how you settled each and on what evidence,
   or why it remains open.
4. **Rankings**: one table with each answer's label, its model, and the rank
   each reviewer gave it.
5. **Actions**: what you changed or delegated, and what still needs the user.

## 5. Act

Act on the decision when the request calls for changes:

- **Obvious:** one correct change, settled by evidence and within the request.
  Make it yourself, or delegate it with `write agent://<member>` to the
  stage-2 member whose answer covered it; that agent already has the context.
  Give one owner per file, and verify the result before reporting it.
- **Uncertain:** a product or design choice, conflicting evidence, a breaking
  or cross-repository change, or irreversible data effects. Do not act:
  ask the user with the `ask` tool, presenting the options with evidence and
  your recommendation first.

Never commit unless the user asked for it.
