---
description: >-
  Research a change, ask only what research cannot settle, then implement it.
  Big changes first get a plan that the council reviews. Commits only on
  request.
argument-hint: "[what to implement]"
---

# Implement

Request: $ARGUMENTS

If the request is empty, reply only "What should I implement?" and end the
turn; run this procedure on the user's next message.

This command replaces the `brainstorming`, `writing-plans`, `executing-plans`,
`subagent-driven-development`, `requesting-code-review` and
`finishing-a-development-branch` skills; don't load them.

## 1. Research

Before asking anything, research: the code the change touches, its callers
and tests, the project's conventions, the version-specific docs of each
library or platform the design rests on, and how others solve the problem
(web search). Use read-only probes (a query, a script, a request) where docs
don't settle behavior. If a user decision determines which code changes,
research each plausible scope enough to explain it, ask, then continue.

Memories, summaries and notes are leads: check a claimed fact against the
code, docs or data, and a claimed decision against the user's messages or the
plan's Requirements.

## 2. Ask only what research cannot settle

Ask only if all three hold:

- the request, earlier answers and research don't settle it;
- it is the user's decision (behavior, scope, priority, what users see) that
  project conventions don't settle, or a fact only the user can reach (a
  private system, an account, data outside the workspace);
- the plausible answers lead to different implementations.

Decide everything else yourself and record it as an assumption. Asking
nothing is normal.

Each round is one `ask` call, never questions in chat. Ask a prerequisite
alone first if its answer could remove other questions. Each question says
what you found and why it is still open, and is `required`:

- a choice: radio group, or checkboxes when several can hold (add "None" if
  valid); each option says what it changes;
- a fact you cannot offer choices for: a text field.

Preselect your recommendation; preselection marks it, so don't label it.

After each round, research what the answers open up and apply the test
again. Stop when nothing passes it and every requirement maps to a behavior a
test or check can confirm.

- If the user answers in chat instead, continue from that answer.
- A result that says the form timed out answers nothing, even with the
  preselected values: report the open questions and end the turn.
- Without an `ask` tool, list the questions in chat and end the turn.
- Outside the test: ask for each approval the Engineering Rules require,
  naming the action; only an explicit approval authorizes it, never a timeout
  or "use your recommendations". When evidence favors a better approach than
  the requested one, recommend it and ask which to build, unless the user
  already made or delegated that choice.

## 3. Size

The change is big if any holds:

- it changes an external contract, stored format, schema or dependency;
- it coordinates behavior across modules or services beyond mechanical caller
  or test updates;
- it needs several steps, each with its own correctness risk;
- you chose between designs with real trade-offs.

Otherwise it is small. State the size and the reason in one line and
continue: small goes to step 5, big to step 4. If a small change turns big
during implementation, stop editing and go to step 4.

## 4. Plan and council (big changes)

1. Write the plan to `local://implement-<slug>.md`:
   - **Requirements:** the request, every answer, every assumption with its
     evidence; no credentials or secrets.
   - **Findings:** facts the design rests on, with `file:line` or a link.
   - **Design:** the chosen approach, the alternatives, and what decides
     between them.
   - **Files and interfaces:** files to create or change; signatures and
     contracts other tasks rely on.
   - **Tasks:** in order, each with the test or check that proves it.
   - **Failure modes:** inputs the Requirements imply that no task covers;
     add a test or check for each to its task.
2. Send questions found while writing through step 2 and fold the answers
   into the plan.
3. Read `skill://council` and run its Answer, Review and Decide stages with
   the request: "Review the plan at <path> against its Requirements. Report
   what would make the implementation wrong, incomplete or needlessly
   complex, with `file:line` or doc evidence, and any question only the user
   can settle. Skip style."
4. Apply the findings that hold. Send the user's decisions through step 2 and
   fold the answers into the plan.

If a user answer or an implementation discovery materially changes a reviewed
part of the plan, repeat items 3 and 4 for that part before implementing it;
applying the council's own findings does not trigger this. If the council
ends with fewer than two answers, report it with the plan path and stop.

## 5. Implement

Implement the small change, or the plan task by task, following
`skill://test-driven-development` for each behavior change. When a test cannot
express the behavior, use a reproducible check showing the old and new
outcome instead of asking.

- If the plan proves wrong, correct it against its Requirements.
- Send questions found while implementing through step 2.
- Before reporting, run the project's checks covering every changed file.

Leave changes uncommitted unless the request asks for a commit.

## Report

1. **Implemented:** behavior, files, and the tests or checks proving it.
2. **Assumptions:** decisions made without asking, with evidence.
3. **Plan** (big changes): path, deviations, and council dissent that
   qualifies the result.
4. **Open or skipped:** what is left and why.
