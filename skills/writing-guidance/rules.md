# omp rules

`~/.omp/agent/rules/<name>.md` (user) or `.omp/rules/<name>.md` (project, read
from the session's working directory only); the filename is the name, and a
project rule replaces the user rule of that name.

| Frontmatter | Reaches the agent |
|---|---|
| `condition` (regex), `astCondition` (ast-grep) or `question` | Injected when an output matches; not listed |
| `alwaysApply: true` | Whole body in every request |
| only `description` | Name and description listed in every request; body through `rule://<name>` |
| none of these | Never |

- A triggered rule is for judgment needed at one moment. Its body is read
  mid-action: the fix first, in a few lines.
- Cover the nearest workarounds in the trigger too: an agent stopped on
  `as any` reaches for `as unknown as T` or `: any` next.
- `condition` matches while the output streams; `condition` and
  `astCondition` can both stop the call before it runs. A `question` is judged
  after the output, so it cannot prevent the action; it costs a judge call per
  in-scope output, and with `ttsr.judge: auto` it is judged only when the
  `judge` role resolves to a native judgment API (TypeSafe, OpenRouter, OpenAI
  or Google Decisions): check `omp config get modelRoles`, or use a
  `condition`. Prefilter a `question` with `condition` and `scope`.
- `scope`: `text`, `thinking`, `tool` or `tool:<name>(<glob>)`, comma-separated;
  without it the rule watches prose and all tool arguments. A `condition` that
  looks like a glob becomes an edit/write scope, so write scopes explicitly.
- On `edit` and `write`, `condition`, `astCondition` and the judge see one
  entry per touched file holding only what the call adds: added lines,
  `new_string` for a replace, the whole content for a write. They never see the
  payload syntax (`[path#TAG]`, `PUT`, a leading `+`, `*** Update File`), so a
  condition anchored on it never fires live. Existing and removed code are
  invisible, so a `question` that needs them raises false alarms.
  `astCondition` works only in files whose extension names a language;
  `ast_edit` changes are invisible to it.
- `globs` require a matching file path; `agents: [main]` limits the rule to the
  top-level session.
- `interruptMode`: `always` (stop the output and re-prompt), `never` (deliver
  after the call: guides follow-up work, cannot prevent a side effect),
  `tool-only` or `prose-only`; unset, `ttsr.interruptMode` decides.
- `repeatMode`: `once` lets every later violation in the session through;
  guardrails use `always` (once per turn) or `after-gap`. Unset,
  `ttsr.repeatMode` decides.
- `/omfg <what went wrong>` drafts a triggered rule from the conversation and
  validates it against recent outputs; review the draft against
  [writing.md](writing.md).

**Checks:**
`python3 "$(realpath skill://testing-guidance/scripts/trial.py)" rules --target <rule.md> --evals <evals.json>`
runs the eval set's `rule_cases`: what the matcher would see (the added lines
of one file, with its `tool` and `path`), which the rule must fire on, and near
misses it must ignore. For a `question` rule it tests scope and prefilter only;
the judge does not run.
`sessions.py cases` ([evaluating-guidance](skill://evaluating-guidance)) turns
a window's real edits into such cases, each listing the rules delivered live,
so offline verdicts can be compared with live delivery.
`omp ttsr scan -r <rule.md> <dir>` takes one directory and skips `question`
rules. Its hits are leads for an over-broad trigger, not a false-positive rate:
a hit outside the rule's intent is a false positive only if an edit adds it.
