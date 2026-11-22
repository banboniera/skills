---
name: evaluating-guidance
description: Use to review omp guidance against real sessions, weekly, after repeated mistakes or upgrades.
---

# Evaluating guidance

The goal is guidance that held up against what agents actually did: every
target judged on evidence from real sessions, the code and primary sources,
the failures it caused or missed fixed, and the fixes verified, in one pass.
How to write and check guidance is [writing-guidance](skill://writing-guidance);
measuring a change by trial runs is [testing-guidance](skill://testing-guidance).

Take the path the request names:

- **Project review:** a project's weekly review, "review this project's
  guidance", or after a model or omp upgrade. Follow [review.md](review.md).
- **Scoped:** a named rule, skill, command or agent, one claim or finding, or a
  repeated mistake. Follow the steps below for those targets only.

Apply the changes unless the request asks only for an assessment. From a
project, change user-level guidance only when asked; otherwise report it.

**Targets:** in the project, every `AGENTS.md` and, under `.omp/`,
`RULES.md`, `WATCHDOG.md`, `WATCHDOG.yml`, `rules/`, `skills/`, `commands/`,
`agents/`, `extensions/`; at user level the same names in `~/.omp/agent/`,
often symlinks (`realpath` shows the repository that owns them).

## Steps

1. **Evidence.** Read the target, what loads it (trigger, description, index
   entry) and the code and configs it describes. To see how it behaved, or to
   find a repeated mistake, digest the sessions that mention it and read them
   per [session-analysis.md](session-analysis.md):

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
      home that reaches the agent before the decision, clearer wording.
3. **Fix** per writing-guidance steps 3 to 5. A check lands before the prose
   it replaces is deleted. Fix code built on wrong guidance too, each fix with
   a test that proves the correct behavior.
4. **Verify** every changed target with the writing-guidance checks, and run
   the project's checks on changed code once, on the final tree. When review
   cannot settle whether a behavior change works, recommend a trial.
5. **Report.** Lead with the result. Then each change with its target and
   evidence, code fixes with their tests, findings not acted on with the
   reason, and the checks with their results. Leave the changes uncommitted
   unless the user asks for a commit.
