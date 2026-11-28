---
name: evaluating-guidance
description: "Use to audit omp guidance in use: right, needed, delivered? Weekly, after mistakes. Not for trials."
---

# Evaluating guidance

The goal is a verdict for every target in scope, each backed by the evidence
that decides it, and only the changes that evidence supports, verified. How to
write and check guidance is [writing-guidance](skill://writing-guidance);
measuring a change by trial runs is [testing-guidance](skill://testing-guidance).

Take the path the request names:

- **Project review:** a project's weekly review, "review this project's
  guidance", or after a model or omp upgrade. Follow [review.md](review.md).
- **Scoped:** a named rule, skill, command or agent, one claim or finding, or a
  repeated mistake. Follow the steps below for those targets only.

**Permissions are separate.** Edit guidance unless the request asks only for
an assessment. From a project, report user-level guidance instead of changing
it, unless asked. Change code, API contracts, settings or another repository
only when the request covers them. Ask before spending money on judge probes
or trials.

**Targets:** the context files omp loads (`AGENTS.md`, `CLAUDE.md` and the
others in omp://context-files.md) and, under `.omp/` and `~/.omp/agent/`,
`RULES.md`, `WATCHDOG.*`, `rules/`, `skills/`, `commands/`, `agents/`,
`extensions/` (`realpath` shows the repository that owns a symlink). A file
that exists is not necessarily loaded: run `omp ttsr list --json` and
`omp skill list --json` in the directory the target's agents work in.

## Steps

1. **Baseline.** Record the starting commit and uncommitted changes, the omp
   version, and which agents (main session, subagents) and directories each
   target serves.
2. **Evidence, cheapest first.** Stop when the next step cannot change the
   verdict.
   1. **Static:** the target, what loads it (trigger, description, index
      entry), the code and configs it describes, and primary docs for its
      technical premise.
   2. **Sessions:** digest them and read them per
      [session-analysis.md](session-analysis.md):

      ```sh
      python3 "$(realpath skill://evaluating-guidance/scripts/sessions.py)" \
        --project <dir> --since <YYYY-MM-DD> --match '<target, task or path words>'
      ```

      The index ends with each rule's deliveries and deliberate reads. Search
      for the tasks and paths the target governs, not only its name: sessions
      where it applied and never appeared are the evidence for "not
      delivered".
   3. **Triggers:** replay the window's real edits in the rule's file scope and
      compare the offline verdicts with what was delivered live:

      ```sh
      cases="$(mktemp -d)/cases.json"  # private: it holds source text from the sessions
      python3 "$(realpath skill://evaluating-guidance/scripts/sessions.py)" cases \
        --project <dir> --since <YYYY-MM-DD> --path '<scope glob>' --out "$cases"
      python3 "$(realpath skill://testing-guidance/scripts/trial.py)" rules \
        --target <rule.md> --evals "$cases"
      ```

      Use the rule's version from that window (`git show <rev>:<rule.md>` into
      a temporary `rules/` directory). `DIFF` lines are edits where offline and
      live disagree; read each before calling it a trigger defect. A rule
      delivered earlier in the same session is usually held back by its
      `repeatMode`. Only single-file edits with exact delivery records are
      scored. Labelled positives and near misses live in the rule's eval set
      ([rules.md](skill://writing-guidance/rules.md)). For a `question` rule
      both test scope and prefilter only; the judge does not run.
   4. **With approval:** a judge probe on the exact per-file payload, or a trial
      per testing-guidance.
3. **Judge each claim** and record:
   - the claim and its authority (the user's policy or a technical fact);
   - **Correct?** against code, tests and primary sources;
   - **Reaches?** the agent that makes the decision, before it makes it;
   - **Needed?** what else covers the same agent, timing and exceptions;
   - **Better?** a check that makes the mistake impossible, a home that
     reaches the agent earlier, clearer words;
   - one disposition: keep, correct, move, replace with a check, remove, add,
     or insufficient evidence.

   Remove only when another home or check covers the same agent, decision time
   and exceptions: a check that reports after the action does not replace
   guidance needed before it, and no observed failure is no evidence that a
   claim is unneeded. For wrong guidance, list the code built under it; fix
   that code only when the intended behavior and the permission are
   established, otherwise report it.
4. **Fix** per writing-guidance steps 3 to 5. A check lands before the prose it
   replaces is deleted; each code fix comes with a test that proves the
   correct behavior.
5. **Verify** every changed target with the writing-guidance checks, and the
   project's checks on changed code, once on the final tree. A changed trigger
   fires on the cases it missed and stays quiet on its near misses. When a
   behavior change still needs measuring, follow testing-guidance: held-out
   cases against the shipped version; read every failed check against its run's
   diff before counting it; keep the shipped version unless the candidate
   wins.
6. **Report.** Lead with the result. Then:
   - one row per target in scope: verdict, action taken, and the evidence for
     each of Correct, Reaches and Needed (the code or source checked, the
     delivery or read records, what else covers it), what remains uncertain;
     "not reviewed" with the reason;
   - for each changed trigger, the replayed edits it missed and its near
     misses, each cited, with the old and the new verdict;
   - explicit answers to "remove anything?" and "add anything?";
   - coverage: targets reviewed of all, sessions analysed of those found;
   - code fixes with their tests, findings not acted on with the reason, and
     the checks with their results;
   - what you cleaned up: services and worktrees you started, digests, trial
     output.

   Cite every delivery, read and incident you count by digest file and line,
   and every replayed edit by the transcript and line `cases` records for it:
   in the report when there are a few, otherwise in an
   evidence file it links, with totals and the deciding examples in the
   report. Deliveries, deliberate reads and need are separate claims. A
   number for what a change would have caught needs a replay; otherwise call
   it an estimate. Leave the changes uncommitted unless the user asks for a
   commit.
