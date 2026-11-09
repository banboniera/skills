# Session analysis

Find the mistakes agents actually made in the window, and which of them guidance
could have prevented. This is error analysis on real transcripts: read, note,
group, count ([Husain](https://hamel.dev/blog/posts/evals-faq/why-is-error-analysis-so-important-in-llm-evals-and-how-is-it-performed.html)).

## Where sessions are

- Main sessions: `~/.omp/agent/sessions/<encoded-cwd>/<timestamp>_<id>.jsonl`.
  `<encoded-cwd>` is the project path under home with `/` replaced by `-`, for
  example `-Documents-HuggingCar-backend`. Include worktree buckets of the same
  project.
- Subagent transcripts: `<session-without-.jsonl>/<AgentId>.jsonl`, nested the
  same way. Advisor reviews: `__advisor*.jsonl` beside them.
- One JSON entry per line. User turns:
  `read <file>.jsonl?q=select(.type=="message" and .message.role=="user") | .message.content[]? | select(.type=="text") | .text`.
  Rule injections: `select(.type=="ttsr_injection")`.

Split the window's sessions across subagents, a few sessions each. Skip
sessions of this skill's own runs.

## What to look for

- The user corrects, rejects or repeats an instruction ("no", "I told you",
  "why did you", swearing), especially the same correction across sessions.
- Work reverted, redone or abandoned; checks that failed and were retried
  without a cause found; long loops on one problem.
- A rule injection or advisor note the agent then ignored, or one that fired on
  the wrong work.
- An agent following guidance that turned out wrong, or asking for information
  guidance or the code already gives.
- A skill that should have loaded and did not (no `read skill://<name>`), or
  one loaded for unrelated work.
- Guidance loaded and contradicted by what the agent did.

## Method

1. **Note.** Per session, write one line for the first thing that went wrong,
   with the session file and a short quote. A session with nothing wrong gets
   no note.
2. **Group.** Cluster the notes into failure modes with plain names
   ("starts services the user said not to touch").
3. **Count.** Sessions per failure mode.
4. **Attribute** each mode to one cause:
   - **missing guidance:** nothing told the agent, and it could not have
     learned it from the code;
   - **wrong guidance:** the agent did what guidance said;
   - **ignored guidance:** guidance was loaded and the agent did otherwise;
   - **not guidance:** model, tool or task problem; report it, change no
     guidance for it.

Report each mode with its count, cause, example sessions and quotes, and the
guidance targets it points at.
