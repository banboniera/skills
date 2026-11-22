---
name: writing-guidance
description: Use when creating or changing an omp skill, rule, slash command, AGENTS.md or RULES.md.
---

# Writing guidance

Read [writing.md](writing.md) before drafting, and the file for the kind you
write: [skills.md](skills.md), [rules.md](rules.md) or
[commands.md](commands.md).

1. **Evidence.** State the failure the guidance fixes, or the procedure the
   user wants captured, with its evidence: session lines, the user's
   correction, the request. Add guidance only for a failure seen twice, one
   costly failure (security, tenancy, money, data loss, irreversible
   operations), or a user request. If you do not know what agents do without
   it, find out first: their sessions
   ([evaluating-guidance](skill://evaluating-guidance)) or a `without` trial
   ([testing-guidance](skill://testing-guidance)).
2. **Form.** Use the strongest fix that works: a check whose failure names the
   fix; a code change that removes the trap; guidance in the home
   [writing.md](writing.md) assigns; nothing, when agents already act right.
   Guidance agents never received needs a home that reaches them; guidance
   they ignored needs a check or an interrupting rule. Extend the topic's
   existing home (`~/.omp/agent/`, `.omp/`, `AGENTS.md`) instead of adding a
   second one.
3. **Draft**, then reread it as an agent that never saw this conversation:
   every step ends on a checkable criterion, every name resolves, and no line
   restates the environment or what the model does anyway.
4. **Static checks:** the checks in the kind's file; every path, command,
   link, `skill://` or `rule://` URL, skill, agent, tool and model the text
   names exists; the frontmatter is valid YAML (omp reads invalid YAML line by
   line and loses multi-line values); before deleting a file, find what uses
   it.
5. **Test** with [testing-guidance](skill://testing-guidance) when the change
   shapes behavior: new guidance, a rewrite, a changed description or trigger,
   a disputed no-op. A corrected fact needs only step 4.
6. **Report** what changed and why, the evidence, the checks and tests with
   their results, and what stays unverified. User-level changes take effect in
   a new session. Leave the changes uncommitted unless asked.
