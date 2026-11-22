# omp rules

`~/.omp/agent/rules/<name>.md` (user) or `.omp/rules/<name>.md` (project); the
filename is the name, and a project rule replaces the user rule of that name.
Changes take effect in a new session.

| Frontmatter | Reaches the agent |
|---|---|
| `condition` (regex), `astCondition` (ast-grep) or `question` | Injected when an output matches; not listed |
| `alwaysApply: true` | Whole body in every request |
| only `description` | Name and description listed in every request; body through `rule://<name>` |
| none of these | Never |

- Use a triggered rule for judgment needed at one moment. Its body is read
  mid-action: the fix first, in a few lines.
- `condition` and `astCondition` match while the output streams and can stop
  it. A `question` is judged after the output, so it cannot prevent the
  action, and costs a judge call per in-scope output: prefilter it with
  `condition` and `scope`.
- `alwaysApply` costs every request; the few invariants every task needs
  belong in `RULES.md`.
- `scope`: `text`, `thinking`, `tool` or `tool:<name>(<glob>)`, comma-separated;
  without it the rule watches prose and all tool arguments. A `condition` that
  looks like a glob becomes an edit/write scope, so write scopes explicitly.
- `astCondition` sees only what an edit or write adds, in files whose
  extension names a language.
- `globs` require a matching file path; `agents: [main]` limits the rule to the
  top-level session.
- `interruptMode: never` delivers the rule after the call: it guides follow-up
  work and cannot prevent a side effect. The default interrupts.
- `repeatMode`: `once` per session, `after-gap`, or `always`.
- `/omfg <what went wrong>` drafts a triggered rule from the conversation and
  validates it against recent outputs; review the draft against
  [writing.md](writing.md).

**Checks:**
`python3 "$(realpath skill://testing-guidance/scripts/trial.py)" rules --target <rule.md> --evals <evals.json>`
runs the eval set's `rule_cases`: snippets the rule must fire on and near
misses it must ignore. A `question` verdict is never judged offline.
`omp ttsr scan -r <rule.md> <dir>` lists every hit in a real tree; a hit outside
the rule's intent is a false positive.
