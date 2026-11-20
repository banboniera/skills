---
name: evaluating-guidance
description: >-
  Reviews omp agent guidance (AGENTS.md, RULES.md, rules, skills, slash
  commands, agent definitions, advisor files) against real sessions, the code
  and primary sources, and fixes what fails. Use for a project's weekly
  guidance review, when an agent repeats a mistake, to check or change a named
  rule, skill or command, and after a model or omp upgrade.
---

# Evaluating guidance

Guidance earns its place only if agents act differently, and correctly, because
of it. Evidence comes from real sessions, the code and primary sources. Do not
build trial runs, sandboxes or benchmarks to test guidance; measuring one
concrete claim, such as how long a check takes, is ordinary evidence.

Take the path the request names:

- **Project review:** a project's weekly review, "review this project's
  guidance", or after a model or omp upgrade. Follow [review.md](review.md).
- **Scoped:** a named rule, skill, command or agent, one claim or finding, a
  repeated mistake, or guidance that another task changes. Follow the steps
  below for those targets only; no review window, no project-wide analysis.

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
      ([writing.md](writing.md)).
3. **Decide** on the strongest fix that works:
   1. a check (test, lint, type, hook) whose failure names the fix; it lands
      before the prose it replaces is deleted;
   2. a code change that removes the trap;
   3. corrected guidance in its one home, written per [writing.md](writing.md);
   4. deletion.

   Add guidance only for a failure seen at least twice, for one costly failure
   (security, tenancy, money, data loss, irreversible operations), or when the
   user asks for it. Match the fix to the cause: guidance that never reached
   the agent needs a home that does; guidance the agent had and ignored needs a
   check or an interrupting rule, not louder words.
4. **Fix code built on wrong guidance**, each fix with a test that proves the
   correct behaviour. Follow the project's own rules for subagents and checks;
   a check runs once per code state.
5. **Verify** what changed:
   - Rule trigger or scope: run
     `omp ttsr test --rule <rule.md> --source tool --tool <edit|write|bash> --path <file> '<snippet>'`
     with a snippet the rule must match and with a near miss it must not.
     `omp ttsr scan -r <rule.md> <dir>` lists where it fires in the tree;
     `omp ttsr list` shows that it registered. None of these judges a
     `question`: test its `condition` and `scope`, and say the verdict is
     untested.
   - Skill: `omp skill list --json` shows it with the description as parsed.
   - Command or agent: the frontmatter parses, and every agent, tool and model
     it names exists.
   - Every path, command, symbol and link in the changed text resolves.
   - Code: the project's checks, once, on the final tree.
   - Before deleting a file, read it and search for what uses it.
6. **Report.** Lead with the result. Then each change with its target and
   evidence, code fixes with their tests, findings not acted on with the
   reason, and the checks run with their results. Leave the changes
   uncommitted unless the user asks for a commit.
