# Session analysis

Find the mistakes agents made in the assigned sessions, and which of them
guidance could have prevented: note each incident, attribute it, then group
and count.

## Reading a digest

The first line is the transcript path; every other line is
`HH:MM:SS L<line> KIND text`, and `### <agent>` sections hold a subagent's
lines. `<digest>.events.jsonl` beside it holds the same events in full, with
their entry ids.

| Kind | Meaning |
|---|---|
| `USER`, `AGENT` | A user turn (`(mid-run)`: sent while the agent worked) and the reply it answers |
| `END` | The last reply of the session or subagent |
| `RULE` | A rule delivery and its mode: `interrupt` (output stopped before the call ran), `tool-reminder` (attached after a batch of calls ran), `judged` (after the output), `unknown` |
| `LOAD` | A read of `skill://` or `rule://`: `body`, `file` (a support file), `listing`, `invoked` or `autoload`, with outcome `ok`, `failed` or `no-result` |
| `EDIT` | A guidance file edited |
| `CHECK` | A failed tool call, with its exit code |
| `TASK` | A subagent's final status and the start of its result |
| `ADVISOR`, `GATE` | An advisor note; a stop-gate message |
| `ABORT`, `ERROR` | A user interrupt; a provider error |
| `COMPACT`, `MODEL` | A context compaction; a model change |

A digest line is a lead. Before noting an incident, read the transcript
around it through the `archive` eval namespace (help://eval/archive), never by
parsing the JSONL: `archive.transcript` first, then `archive.messages` for
whole entries. Advisor notes, reviewer findings and agents' own claims of
success are claims to check. Runs of this skill count like any other session.

## What to look for

- The user corrects, rejects or repeats an instruction ("no", "I told you",
  "why did you", swearing, an `ABORT`, a `(mid-run)` turn), especially the same
  correction across sessions.
- Work reverted, redone or abandoned; `CHECK` failures retried without a cause
  found; long loops on one problem.
- A rule delivered and then not followed, or delivered on unrelated work (the
  matched text shows it).
- An agent following guidance that turned out wrong, or asking for
  information the guidance or the code already gives.
- A task a target governs where its `RULE` or `LOAD` never appears.

## Method

1. **Note** each incident: digest file, line, a short quote, the agent and
   the decision, what it did, and what should have happened with the evidence
   for that. A session holds many tasks; note all of them, not the first. A
   provider error that a fallback recovered is one "not guidance" note in
   total.
2. **Attribute** each incident to a cause, with the evidence it needs; one
   incident can have several:
   - **missing:** nothing told the agent, and the code could not have;
   - **wrong:** quote the guidance line and the action that followed it;
   - **not delivered:** the guidance existed, but this agent had none of it
     before the decision: no `RULE`, no `LOAD` of any kind, no always-loaded
     file for this agent (a subagent gets no `AGENTS.md`). A `tool-reminder`
     or `judged` rule arrives after the call it is about;
   - **ignored:** delivered to the same agent, on the same branch, before the
     decision, and the agent did otherwise;
   - **not guidance:** a model, tool or task problem; report it, change no
     guidance for it;
   - **unknown:** the evidence cannot decide; say what is missing (a pruned
     message, a compaction, a subagent without a transcript).
3. **Group** the incidents into failure modes with plain names ("starts
   services the user said not to touch").
4. **Count** incidents and distinct sessions per mode, and say what each count
   counts. Deliveries, deliberate reads and incidents are different counts; a
   missing record proves only that the digest lacks it.

## Report

One row per failure mode: name, incidents and sessions, cause with its
evidence, examples (digest file, line, quote), and the guidance targets it
points at.
