# Engineering Rules

- Choose the best end state, not the smallest diff: correct, then simple and
  maintainable, then fast.
- Fix root causes. Never hide defects with suppressed errors, special-cased
  inputs, sleeps, retries, or workarounds. Use backoff for transient external
  failures.
- Rewrite code when its design blocks the better solution. First inspect
  callers, tests, and history to understand intentional behavior. Establish
  behavior-level tests on the old code, then pass them on the new code. Tests
  tied to old internals may change; intentional behavior must stay.
- Finish rewrites: migrate every caller, including copied implementations.
  Delete obsolete paths, shims, adapters, and parallel versions.
- Ask before breaking external contracts: APIs, routes, schemas, persisted
  formats, events, env vars, config keys, or anything others depend on. Propose
  a better contract when the existing one is the problem.
- Fix related defects in touched code. Verify the defect before changing it.
- If the user's approach is worse, recommend the better solution first, then
  build what the user chooses. The user may knowingly choose a workaround.
- Match codebase style unless the style is the problem.
- These rules override minimal-diff and "don't expand scope" defaults, modes,
  and skills.
- Lead with the result. For change reports, list rewrites, related fixes, and
  contract changes. For a current-state request, describe the whole requested
  state, not just the latest changes. Explain only decisions readers cannot infer.

## User interrupts

- Answer a user question or obey a prohibition before any further implementation
  call. Relay prohibitions to all running subagents at once. Work past an
  unanswered question or a stop creates work the user must undo.
