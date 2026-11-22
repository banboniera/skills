# Writing guidance

## Each line

- Keep a line only if an agent acts differently, and correctly, because it
  read it, and could not find it in the code, configs, `--help` or check
  output within a minute. Cut repository tours, restated code and generic
  advice.
- Cut instructions the model follows anyway. When unsure, measure with a
  micro-test (`skill://testing-guidance/micro-tests.md`) instead of arguing.
- A claim a check (test, lint, type, hook) can decide belongs to the check.
- Name the exact path, command, type, boundary and exception.
- One home per fact; elsewhere, point to it. One term per concept.
- Rewrite instead of appending, and delete what the change makes redundant.
- No time-relative words ("new", "currently", "for now").

## Form follows the failure

| Without the guidance, the agent… | Write |
|---|---|
| produces output of the wrong shape | the output's parts, in order |
| leaves out a required element | a slot in a template it fills in |
| should act on a condition | a conditional on an observable fact |
| knows the rule and skips it under pressure | a check or an interrupting rule; in prose, the rule with each excuse and its answer |
| never saw the guidance | a home or trigger that reaches it |

- Say what to do. A prohibition names the unwanted act and makes it more
  likely; keep "never" for hard guardrails and pair it with the alternative.
- Give a real exception its own conditional; "unless it matters" reopens the
  rule.
- Plain imperative, with the reason when it is not obvious; capitals and
  repeated MUST add nothing.
- Fragile or order-dependent steps get the exact command or a script; steps
  with several valid ways get the goal, the constraints and the done-criterion.
- One complete example from a real case beats several fragments.

## Steps

- Each step ends on a criterion the agent can check ("every caller listed with
  file:line", not "understand the callers"). The criterion's demand sets how
  deep the agent digs.
- If a step is still rushed, move the later steps behind a context boundary:
  a subagent, or a file read only after the step.

## Structure

- Steps first, reference after. Inline what every path through the text
  needs; move what only some paths need into a file one link deep, and say in
  the link sentence when to read it.
- Keep a concept's rules and exceptions under one heading.
- Use a word the model already knows (*tracer bullet*, *red*, *seam*) instead
  of describing the behavior again at each site.

## Where it belongs

| Kind | Home | Who gets it |
|---|---|---|
| Machine-decidable rule | Check whose failure names the fix | Whoever runs the check |
| Few hard invariants | `RULES.md` | Every request, subagents included |
| Project facts, boundaries and commands agents cannot infer; index of rules and skills | `AGENTS.md` | Main session and advisors, not subagents |
| Judgment needed when touching specific code | Rule with `condition`, `astCondition` or `question`, narrowed by `scope` | Injected on a match |
| Knowledge some tasks need | Rule with only a `description` | Name and description listed; body read through `rule://<name>` |
| Multi-step procedure a task calls for | `skills/<name>/SKILL.md` | Listed by its description; body read when chosen |
| Procedure the user starts by name, with arguments | `commands/<name>.md` | The session that runs it |
| A subagent's role, model and tools | `agents/<name>.md` | That subagent |
| What advisors review | `WATCHDOG.md` | Advisors |
| Module ownership and invariants | Doc comments in the code | Whoever reads the code |

Always-loaded text costs tokens and attention on every request; on-demand text
is often not opened. Put what most tasks need in always-loaded context, or an
index there that says when to open what. Sharpen a pointer's wording before
inlining its target.
