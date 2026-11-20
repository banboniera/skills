# Writing guidance

Agents treat guidance as context, not enforced configuration; short, specific
and consistent guidance is followed more reliably
([Claude Code docs](https://code.claude.com/docs/en/memory#write-effective-instructions)).

## What earns a line

- Keep a line only if an agent acts differently, and correctly, because it
  read it, and could not learn it from code, configs or check output within a
  minute. Repository tours, restated code and generic advice add cost without
  benefit ([Gloaguen et al.](https://arxiv.org/abs/2602.11988)).
- If a check (test, lint, type, hook) can decide a claim, the check owns it.
- Name the path, command, type, boundary and exception.
- One home per fact; point to it instead of copying. One term per concept.
- Rewrite, do not append: fold the change into the text, cut what it makes
  redundant, and rewrite the file when a patch would leave it inconsistent.
- Cut every word that does not change what the agent does.
- Calm wording ("Use X when…"), the reason in a clause when it is not obvious.
  Absolute words only for hard rules.
- No time-relative words ("new", "currently", "for now").

## Where it belongs

| Kind | Home | Who gets it |
|---|---|---|
| Machine-decidable rule | Check whose failure names the fix | Whoever runs the check |
| Few hard invariants | `RULES.md` | Every request, subagents included |
| Non-inferable project facts, boundaries, commands; index of rules and skills | `AGENTS.md` | Main session and advisors; not subagents |
| Judgment needed when touching specific code | Rule with `condition`, `astCondition` or `question`, narrowed by `scope` | Injected on a match; not listed in the prompt |
| Knowledge some tasks need | Rule with only a `description` | Listed by name and description; body read through `rule://<name>` |
| Multi-step procedure a task calls for | `skills/<name>/SKILL.md` | Listed by a hint; body read when the agent picks it |
| Procedure the user starts by name | `commands/<name>.md` | The session that runs the command |
| A subagent's role, model and tools | `agents/<name>.md` | That subagent |
| What advisors review | `WATCHDOG.md` | Advisors only |
| Module ownership and invariants | Doc comments in the code | Whoever reads the code |

On-demand material is often not opened
([Vercel](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)):
knowledge needed broadly goes in always-loaded context, or in an index there
that says exactly when to open what.

## omp mechanics

Checked against `omp://rulebook-matching-pipeline.md`,
`omp://ttsr-injection-lifecycle.md`, `omp://skills.md` and
`omp://context-files.md`; recheck after an omp upgrade.

- A rule with `alwaysApply: true` and no trigger is in every request. A rule
  with no trigger, no `alwaysApply` and no `description` never loads.
- `scope` limits a trigger to `text`, `thinking` or `tool:<name>(<glob>)`;
  without it the rule watches prose and all tool arguments. `agents:` limits a
  rule to named agents (`main` is the top-level session).
- A match interrupts the output before the tool call runs.
  `interruptMode: never` delivers the rule after the call instead: it guides
  follow-up work and cannot prevent a side effect.
- `repeatMode: once` fires a rule once per session; the default comes from the
  `ttsr.repeatMode` setting.
- A `question` costs a judge call per in-scope output; prefilter it with
  `condition` and `scope`.
- Rule edits take effect in the next session (`/new`).
- The model's skill list shows a routing hint of at most 160 characters
  compressed from `description`, not the description. Write the description in
  third person: what the skill does, then when to use it, in the words a task
  would contain.
- A skill without a `description` is dropped. Invalid frontmatter YAML is read
  line by line, which cuts a multi-line value to its first line; use a block
  scalar (`>-`).
- `disable-model-invocation: true` hides a skill from the model; use it for
  dangerous procedures, which also verify target and approval themselves.
- Keep a skill body short: details in files linked one level deep, exact
  commands for fragile steps, scripts for repeated deterministic steps.

## After the edit

A changed trigger, scope or description, and a new or deleted file, need the
checks in step 5 of [SKILL.md](SKILL.md).
