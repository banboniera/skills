# Session analysis

Find the mistakes agents made in the assigned sessions, and which of them
guidance could have prevented: note, group, count.

## Reading a digest

The first line is the transcript path; every other line is
`HH:MM:SS L<line> KIND text`. `(mid-run)` marks a user turn sent while the
agent was working; `GATE` is an extension stop-gate message; `RULE` lines say
whether the rule interrupted the output (with the matched text) or was
delivered after the call; `(failed)` after `LOAD` or `EDIT` means the tool
call returned an error. Sections headed `### <agent>` hold a subagent's lines.

A digest line is a lead. Before noting a failure, read the transcript around
it: `read <transcript>:<line>`, or `read <transcript>:raw:<line>-<line>` for
one whole entry. Advisor notes and reviewer findings are claims to check, not
observed failures. Runs of this skill count like any other session.

## What to look for

- The user corrects, rejects or repeats an instruction ("no", "I told you",
  "why did you", swearing, an `ABORT`, a `(mid-run)` turn), especially the same
  correction across sessions.
- Work reverted, redone or abandoned; checks that failed and were retried
  without a cause found; long loops on one problem.
- A rule injection or advisor note the agent then ignored, or a rule that
  fired on unrelated work (the matched text shows it).
- An agent following guidance that turned out wrong, or asking for information
  the guidance or the code already gives.
- A skill that should have loaded and did not (no `LOAD` line), or one loaded
  for unrelated work.

## Method

1. **Note** each user correction, rejection or repeated instruction, and each
   failure the user had to point out: digest file, line, a short quote, and
   what the agent did wrong. A session holds many tasks; note all of them, not
   the first. A provider error that a fallback recovered is one "not guidance"
   note in total.
2. **Group** the notes into failure modes with plain names ("starts services
   the user said not to touch").
3. **Count** occurrences and distinct sessions per mode from your notes, and
   say what each count counts.
4. **Attribute** each mode to one cause, with the evidence it needs:
   - **missing:** nothing told the agent, and the code could not have;
   - **wrong:** quote the guidance line and the action that followed it;
   - **not delivered:** the guidance existed but did not reach this agent
     before the action: a subagent without `AGENTS.md`, a skill with no `LOAD`
     line, a rule delivered after the call;
   - **ignored:** the guidance was in context (always loaded, or a `RULE` or
     `LOAD` line before the action) and the agent did otherwise;
   - **not guidance:** a model, tool or task problem; report it, change no
     guidance for it;
   - **unknown:** the transcript cannot show which.

## Report

One row per failure mode: name, occurrences and sessions, cause with its
evidence, examples (digest file, line, quote), and the guidance targets it
points at.
