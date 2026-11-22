# omp skills

- **Path:** `~/.omp/agent/skills/<name>/SKILL.md` (user) or
  `.omp/skills/<name>/SKILL.md` (project), exactly one level under `skills/`.
  Frontmatter `name` equals the directory name: lowercase letters, digits,
  hyphens, at most 64 characters.
- **Description:** required. The model sees it verbatim only when it is 100
  characters or fewer; a longer one is compressed by the smol model into a
  hint of about 12 words, and until then cut to its first 100 characters.
  Write the line yourself: at most 100 characters, in the words a request
  would contain, one trigger per case the skill handles, and what separates it
  from overlapping skills.
- **Invocation:** by default the skill costs one listed line in every request
  and the agent picks it itself. `disable-model-invocation: true` removes it
  from the list; only `/skill:<name> [args]` or a `skill://<name>` link reaches
  it. Use that for procedures only the user should start. A listed skill whose
  steps cost money asks before spending.
- **Body:** what to do once chosen; it repeats nothing from the description.
  Under 500 lines; what only some tasks need goes into files one link deep,
  each link saying when to read it. Run bundled scripts as
  `python3 "$(realpath skill://<name>/scripts/<script>)"`.
- **Subagents** see the same skill list; `autoloadSkills: [<name>]` in an agent
  definition injects one.

**Checks:**
`omp skill list --json | jq '.skills[] | select(.name == "<name>")'` shows it
as parsed;
`python3 "$(realpath skill://testing-guidance/scripts/trial.py)" hint --target <skill dir>`
prints the line the model sees.
