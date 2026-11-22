# omp skills

- **Path:** `~/.omp/agent/skills/<name>/SKILL.md` (user) or
  `.omp/skills/<name>/SKILL.md` (project, read from the session's working
  directory), exactly one level under `skills/`. Use the directory name as
  `name`: lowercase letters, digits and hyphens, at most 64 characters, which
  `omp skill publish` requires.
- **Description:** required. It states only when to use the skill: the
  requests and situations, in the words they would contain, one per case, and
  what separates it from overlapping skills. A summary of the steps there
  becomes the agent's shortcut and the body goes unread. The model sees it
  verbatim only at 100 characters or fewer; a longer one is compressed into a
  hint of about 12 words, and until then cut at 100 characters.
- **Invocation:** by default the skill costs one listed line in every request
  and the agent picks it itself. `disable-model-invocation: true` (or
  `hide: true`) removes it from the list: `/skill:<name> [args]`, a
  `skill://<name>` link and an agent's `autoloadSkills` still reach it, and
  its description is then for people. Use that for procedures only the user
  should start. A listed skill whose steps cost money asks before spending.
- **Body:** what to do once chosen. Under 500 lines; what only some tasks need
  goes into files one link deep, each link saying when to read it. Run
  bundled scripts as `python3 "$(realpath skill://<name>/scripts/<script>)"`.

**Checks:**
`omp skill list --json | jq '.skills[] | select(.name == "<name>")'` shows it
as parsed;
`python3 "$(realpath skill://testing-guidance/scripts/trial.py)" hint --target <skill dir>`
prints the line the model sees.
