---
name: evaluating-guidance
description: >-
  Reviews a project's agent guidance (AGENTS.md, .omp/RULES.md, rules, skills):
  mines recent agent sessions for repeated mistakes, checks every claim against
  the code and primary sources, replaces prose with checks where possible, fixes
  code built on wrong guidance, and hands over the diff. Used for the weekly
  guidance review, before adding, rewriting or deleting a rule or skill, when an
  agent repeats a mistake, or after a model or omp upgrade.
---

# Evaluating guidance

Guidance earns its place only if agents act differently, and correctly, because
of it. Evidence comes from real sessions, the code and primary sources, not from
new trial runs. One run fits in one working session: the root agent applies the
changes and hands the user a report and the full diff; the user commits.

**Targets:** `AGENTS.md`, `.omp/RULES.md`, `.omp/WATCHDOG.md`, `.omp/rules/`,
`.omp/skills/` and their files.

**Window:** sessions since the last run, which is the last commit whose subject
starts with `guidance review`. On the first run, the last 14 days.

## 1. Gather evidence

Run these in parallel as read-only subagents; they report, the root decides.

1. **Sessions.** Error analysis of the window's sessions per
   [session-analysis.md](session-analysis.md): a list of failure modes, each
   with a count, example sessions and a cause (missing, wrong or ignored
   guidance, or not a guidance problem).
2. **Audit.** Mechanical checks over all targets:
   - every path, command, symbol, link, setting and rule trigger resolves
     (grep or glob it);
   - no two targets contradict each other or state the same fact;
   - no time-relative words ("new", "currently", "for now");
   - always-loaded size: lines of `AGENTS.md`, `RULES.md` and every rule
     without a trigger.
3. **Claim review.** Each claim, in this order, citing code and sources:
   1. **Needed?** If the agent learns it anyway from code, types, tests, check
      output or another target, suggest dropping it (or keeping one home) and
      stop.
   2. **Correct?** Check it against the code, tests and configs, and its
      technical premise against current official docs and primary sources. If
      wrong, give the correction and list the code built under it.
   3. **Better?** A test, lint, type, hook or code change that makes the mistake
      impossible; clearer wording per [writing-guidance.md](writing-guidance.md);
      a better home.

   Review targets changed since the last run, targets the session analysis
   implicates, and a rotating quarter of the rest, so every target is reviewed
   about once a month.

## 2. Decide and apply

The root agent reads all evidence, then for each finding picks the strongest fix
that works:

1. A check (test, lint, type, hook) that makes the mistake impossible. It lands
   before the prose it replaces is deleted.
2. A code change that removes the trap.
3. Corrected guidance in its one home, per [writing-guidance.md](writing-guidance.md).
4. Deletion.

Add guidance only for a failure seen at least twice, or once when it is costly
(security, tenancy, money, data loss, irreversible operations). Ignored guidance
needs a stronger home (a check, a hook, `RULES.md`, the index), not louder words.

## 3. Fix code built on wrong guidance

Fixers, one subagent per code area, refactor code built under guidance that was
dropped or corrected; each fix comes with a test that proves the correct
behavior. Fixers change only code and report guidance findings to the root.
Follow the project's own multi-agent and verification rules: who runs checks,
and that each check runs once per code state.

## 4. Verify

- The project's own checks on the final tree, once.
- Each changed rule trigger: grep it against files it must match and must not.
- Each changed skill description: compare it with the session prompts where the
  skill should or should not have loaded.
- One review pass (step 1.3) over the changed targets only. Repeat steps 2–4
  only if it finds something.

For a new or rewritten skill that drives a costly procedure, you may also run 2–3
realistic prompts as parallel subagents with the old and the new version, and
compare the transcripts blind. That takes minutes; do not build sandboxes,
benchmarks or statistics.

## 5. Report

Lead with the result. List:

- failure modes found, with counts and example sessions;
- guidance deleted, corrected, moved, replaced by checks, or added, with the
  evidence for each;
- code fixes and the tests that prove them;
- findings deferred or rejected, with the reason;
- checks run and their results.

Then give the full diff and the suggested commit subject
`guidance review YYYY-MM-DD`.
