# Project review

Review one project's guidance against what agents did since the last review.
You decide and edit; subagents gather evidence read-only and report.

## 1. Window

From the project root:

```sh
python3 "$(realpath skill://evaluating-guidance/scripts/sessions.py)"
```

It prints the window, one row per session with user turns in it, the directory
holding one digest per session, and a report line. The window starts where the
last review of this project ended; `--since` overrides it.

To review user-level guidance, run it in the repository that owns it with
`--since <date>` and `--project <dir>` for each project whose sessions should
count. Such a run has no stored window and prints no report line.

A **full review** claim-reviews every target in step 2.3. Run one when the
script finds no earlier review, after a model or omp upgrade, or when the user
asks for it.

## 2. Gather evidence

Run these in parallel as read-only subagents, at most six in all. They may
have no shell: give each analyst its digest paths, and the auditor the output
of `omp ttsr list` and `omp skill list --json`.

1. **Sessions.** Split the digests across up to four analysts, about 1,500
   digest lines each (the index gives lines per digest); beyond that, take
   the newest sessions and say how many were left out. Each analyst follows
   [session-analysis.md](session-analysis.md).
2. **Audit**, over all targets:
   - every path, command, symbol, link and setting resolves; every rule with a
     trigger and every skill appears in those lists;
   - no two targets contradict each other or state the same fact, user-level
     guidance included;
   - no time-relative words ("new", "currently", "for now");
   - rules that never load: no trigger, no `alwaysApply`, no `description`;
   - what every request carries: lines of each `AGENTS.md`, each `RULES.md`
     and each `alwaysApply` rule, and the number of rulebook rules and skills
     (one listed line each). An always-loaded file over 200 lines is a finding.
3. **Claim review**, step 2 of [SKILL.md](SKILL.md), citing code and sources
   for each verdict, of:
   - targets changed in the window
     (`git log --since=<window start> --name-only -- <targets>`, plus
     uncommitted changes);
   - targets that describe code changed in the window;
   - targets the session analysis or the audit implicates, started when those
     reports arrive.

## 3. Decide and apply

Read all the evidence. Reports are claims: before acting on a failure mode,
open one of its cited transcript lines and check what its count counts. Then
follow steps 3 and 4 of [SKILL.md](SKILL.md). For code fixes, use one fixer
subagent per code area; fixers change only code and report guidance findings
to you.

## 4. Report

Lead with the result. Then:

- the window, and the sessions and user turns analysed;
- failure modes as a table: mode, occurrences and sessions, cause, one example
  (digest file and line), action taken;
- each guidance change (deleted, corrected, moved, replaced by a check, added)
  with its evidence;
- code fixes and the tests that prove them;
- findings not acted on, with the reason: deferred, rejected, or about
  user-level guidance another repository owns;
- checks run and their results;
- as the last line, and only when the review is complete, the script's report
  line verbatim (`guidance-review-window <since> <until> <project>`). The next
  review of the project starts there.

Leave the changes uncommitted unless the user asks for a commit.
