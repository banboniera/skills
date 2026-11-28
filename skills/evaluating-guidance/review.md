# Project review

Review one project's guidance against what agents did since the last review.
You decide and edit; subagents gather evidence read-only and report.

## 1. Window

From the project root:

```sh
python3 "$(realpath skill://evaluating-guidance/scripts/sessions.py)"
```

It prints the window and where it starts (the window recorded by the last
complete review, else the last 14 days), one row per session, each rule's
deliveries, and the directory holding one digest per session. `--since`
overrides the start.

To review user-level guidance, run it in the repository that owns it with
`--since <date>` and `--project <dir>` for each project whose sessions should
count. Such a run cannot be recorded.

Declare the review before gathering:

- **Full:** every target gets a verdict. Run one when no window is recorded,
  after a model or omp upgrade, or when the user asks.
- **Incremental:** targets changed in the window
  (`git log --since=<window start> --name-only -- <targets>`, plus uncommitted
  changes), targets that describe code changed in the window, and targets the
  evidence implicates.

## 2. Gather evidence

Run these as read-only subagents in parallel, as many as the user asks for.
Give every one the same digest directory and starting commit. Subagents may
have no shell: give analysts their digest paths, and the auditor the command
output it needs.

1. **Sessions.** Split the digests across analysts, about 1,500 digest lines
   each (the index gives lines per digest). Each follows
   [session-analysis.md](session-analysis.md). Analyse every session; if some
   cannot be, list them, and the window is not recorded.
2. **Triggers.** Run each triggered rule's eval set `rule_cases` (free, fast).
   Replay real edits (step 2.3 of [SKILL.md](SKILL.md)) only for a rule with a
   delivery question the sessions raised: a task it governs where it never
   fired, or a firing on unrelated work. Limit the replay to the rule's paths
   and the sessions in question, and report what was replayed.
3. **Audit**, over all targets, from `omp ttsr list --json`,
   `omp skill list --json` and `omp config get` run where the agents work:
   - every path, command, symbol, link and setting resolves; every rule with a
     trigger and every skill appears in those lists;
   - no two targets contradict each other or state the same fact, user-level
     guidance included;
   - no time-relative words ("new", "currently", "for now");
   - rules that never load: no trigger, no `alwaysApply`, no `description`;
   - what every request carries: lines of each always-loaded file, and the
     number of listed rules and skills. Size is a lead, not a finding.
4. **Claim review**, step 3 of [SKILL.md](SKILL.md) with sources for each
   verdict, of the targets the declared review covers. Implicated targets
   start when the reports that implicate them arrive.

## 3. Decide and apply

Reports are claims. Before acting on a finding, open the transcript entries
behind it ([session-analysis.md](session-analysis.md)) and check what each
count counts; verify every entry behind a count you report or a removal you
make. Then follow steps 4 and 5 of [SKILL.md](SKILL.md). For code fixes, use
one fixer subagent per code area; fixers change only code and report guidance
findings to you.

## 4. Report and record

Report per step 6 of [SKILL.md](SKILL.md), with the window and the failure
modes as a table: mode, incidents and sessions, cause, one example (digest
and line), action taken.

When every session in the index was analysed and every target the declared
review covers has a verdict, record the window; the next review starts where
it ends:

```sh
python3 "$(realpath skill://evaluating-guidance/scripts/sessions.py)" record <digest dir>
```

Otherwise do not record, and list what was left out.
