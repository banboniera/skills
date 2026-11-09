# Writing guidance

Agents treat guidance as context, not enforced configuration; specific, short
and consistent guidance is followed more reliably
([Claude Code docs](https://code.claude.com/docs/en/memory#write-effective-instructions)).

## What earns a line

Keep a line only if an agent acts differently, and correctly, because it read
it, and could not learn it from code, configs or check output within a minute.
Delete repository tours, restated code and generic advice: they add cost without
benefit ([Gloaguen et al.](https://arxiv.org/abs/2602.11988)).

- If a check (test, lint, CI) can decide a claim, the check owns it.
- Specific beats vague: name the path, command, type, boundary and exception.
- One home per fact; point to it instead of copying.
- One term per concept across all files.
- No time-relative words ("new", "currently", "for now").
- Calm wording ("Use X when…"); add the reason in a clause when it is not
  obvious. Reserve absolute words for real hard rules.

## Where it belongs

| Kind | Home |
|---|---|
| Machine-decidable rule | Check whose failure message names the fix |
| Few hard invariants every agent and subagent holds | `.omp/RULES.md` (always loaded, subagents included) |
| Non-inferable product facts, boundaries, commands, index of rules and skills | `AGENTS.md` (main session; subagents do not get it) |
| Judgment needed when touching specific code | `.omp/rules/<name>.md`, triggered by `condition`/`scope` |
| Multi-step procedure a task calls for | `.omp/skills/<name>/SKILL.md` |
| Module ownership and invariants | Doc comments in the code |

On-demand material is often not opened ([Vercel](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)):
knowledge needed broadly goes in always-loaded context or an index that says
exactly when to open what.

## omp mechanics

- Rules with `condition`, `astCondition` or `question` are injected only when
  matched and are not listed in the prompt; agents learn they exist from the
  AGENTS.md index. Verify every trigger alternative against the code with grep.
- `interruptMode: never` delivers a rule after the matching tool call ran; it
  guides follow-up work and cannot prevent a side effect.
- Judged `question` rules cost a judge call per eligible output; prefilter with
  `condition` and `scope`.
- Skill `description`: third person, what it does and when to use it, in the
  words a task would contain; YAML block scalar (`>-`). An unparseable
  description silently drops the skill.
- `disable-model-invocation: true` hides a skill from the model; use it for
  dangerous procedures, which also verify target and approval themselves.
- Skill body short; details in files linked one level deep; exact commands for
  fragile steps; scripts for repeated deterministic steps.
