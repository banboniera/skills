---
name: evaluating-guidance
description: Use to review omp guidance against real sessions, weekly, after repeated mistakes or upgrades.
---

# Evaluating guidance

Review deployed agent guidance against what agents did with it, and fix what
fails. Guidance earns its place only if agents act differently, and correctly,
because of it. The evidence is real sessions, the code and primary sources.
Two skills own the rest:

- [writing-guidance](skill://writing-guidance): when guidance earns a place,
  its form and home, the writing criteria, and the static checks.
- [testing-guidance](skill://testing-guidance): trial runs, for a change to
  behavior that review cannot settle.

Take the path the request names:

- **Project review:** a project's weekly review, "review this project's
  guidance", or after a model or omp upgrade. Follow [review.md](review.md).
- **Scoped:** a named rule, skill, command or agent, one claim or finding, or a
  repeated mistake. Follow the steps below for those targets only; no review
  window, no project-wide analysis.

Apply the changes unless the request asks only for an assessment. From a
project, change user-level guidance only when asked; otherwise report the
finding.

## Guidance

- Project: every `AGENTS.md`, and in `.omp/`: `RULES.md`, `WATCHDOG.md`,
  `WATCHDOG.yml`, `rules/`, `skills/`, `commands/`, `agents/`, `extensions/`.
- User level: the same names in `~/.omp/agent/`. They are often symlinks;
  `realpath` shows the repository that owns them.

Scripts, extensions and fixtures that belong to guidance are code: judge the
text they show agents as guidance and the rest as code.

## Steps

1. **Evidence.** Read the target, what loads it (trigger, description, index
   entry) and the code and configs it describes. To see how it behaved, or to
   find a repeated mistake, digest the project's sessions whose digest
   mentions it and read them per [session-analysis.md](session-analysis.md):

   ```sh
   python3 "$(realpath skill://evaluating-guidance/scripts/sessions.py)" \
     --project <dir> --since <YYYY-MM-DD> --match '<rule, skill or file name>'
   ```

2. **Judge each claim** in this order; a claim that is not needed is dropped
   without the later questions:
   1. **Needed?** If the agent learns it anyway from code, types, tests, check
      output or another target, drop it, or keep one home.
   2. **Correct?** Check it against the code, tests and configs, and its
      technical premise against current official docs and primary sources. If
      it is wrong, correct it and list the code built under it.
   3. **Better?** A check or code change that makes the mistake impossible, a
      home that reaches the agent before the decision, clearer wording
      ([writing.md](skill://writing-guidance/writing.md)).
3. **Decide** on the strongest fix that works, under the conditions of
   writing-guidance steps 1 and 2: a check whose failure names the fix, a code
   change that removes the trap, corrected guidance in its one home, or
   deletion. A check lands before the prose it replaces is deleted. Write
   changed guidance per writing-guidance step 3.
4. **Fix code built on wrong guidance**, each fix with a test that proves the
   correct behaviour. Follow the project's own rules for subagents and checks;
   a check runs once per code state.
5. **Verify** what changed: the static checks of writing-guidance step 4 for
   every changed target, a trial per testing-guidance for a behavior change
   review cannot settle, and the project's checks on code, once, on the final
   tree.
6. **Report.** Lead with the result. Then each change with its target and
   evidence, code fixes with their tests, findings not acted on with the
   reason, and the checks run with their results. Leave the changes
   uncommitted unless the user asks for a commit.
