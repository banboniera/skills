---
name: writing-guidance
description: Use when creating or changing an omp skill, rule, slash command, AGENTS.md or RULES.md.
---

# Writing guidance

The goal is guidance that makes agents act differently, and correctly, in the
situation it was written for, and nothing else: no line an agent would not
miss. Read [writing.md](writing.md) before drafting, and the file for the
kind you write: [skills.md](skills.md), [rules.md](rules.md) or
[commands.md](commands.md).

1. **Evidence.** Name the failure the guidance fixes, or the procedure to
   capture, with its source: session lines, the user's correction, the
   request. A procedure from this conversation comes from its transcript: the
   steps, commands, tools and corrections as they happened. Add guidance only
   for a failure seen twice, one costly failure (security, tenancy, money,
   data loss, irreversible operations), or a user request.
2. **Existing guidance.** Search the guidance that loads where the failure
   happened (`~/.omp/agent/`, the project's `.omp/`, every `AGENTS.md` on the
   path) for the topic. If something covers it, find out why it did not work
   (`omp ttsr test` shows whether a rule fires) and fix that one; a second
   home for the same topic splits the agent's attention.
3. **Form.** Use the strongest fix that works: a check whose failure names the
   fix; a code change that removes the trap; guidance in the home
   [writing.md](writing.md) assigns; nothing, when agents already act right.
4. **Draft**, then reread it as an agent that never saw this conversation:
   the goal is clear, every step ends on something checkable, every name
   resolves, and no line restates what the environment shows.
5. **Check** with the checks in the kind's file. Every path, command, link,
   `skill://` or `rule://` URL, skill, agent, tool and model the text names
   exists; the frontmatter is valid YAML (omp reads invalid YAML line by line
   and loses multi-line values); before deleting a file, find what uses it.
6. **Report** what changed and why, the evidence, the checks and their
   results. For new or rewritten guidance that shapes behavior, recommend a
   trial with [testing-guidance](skill://testing-guidance) and run it only if
   the user approves its cost. Leave the changes uncommitted unless asked.

A changed skill body is read from disk on the next `skill://` read; a new
skill resolves through `skill://` at once. Descriptions in the skill list,
rules and commands change in the next session (`/new`).
