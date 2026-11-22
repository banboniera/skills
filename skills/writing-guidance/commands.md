# omp slash commands

A command is a one-file procedure the user starts by name, with arguments.
Make it a skill instead when it needs bundled files or the agent must reach it
on its own.

`~/.omp/agent/commands/<name>.md` (user) or `.omp/commands/<name>.md`
(project, wins on the same name); the filename is the name.

Frontmatter: `description` (the autocomplete line), `argument-hint` (ghost
text after the name), `side: true` (runs as a `/btw` side question: off the
transcript, never steering the session; for read-only questions about it).

Arguments are substituted once, before the model sees the body:

- `$1`, `$2`, …; `$@[2]` is every argument from the second on, `$@[2:3]` three
  of them; `$ARGUMENTS` and `$@` are all of them.
- Arguments split at spaces; quotes keep spaces; there are no backslash
  escapes; empty quoted arguments are dropped.
- A missing argument becomes an empty string; a body without placeholders gets
  the arguments appended.

Say in the body what to do when an argument is empty. The body is the
procedure the session follows: steps with completion criteria, report format
last.

**Checks:** every placeholder follows the rules above. In trials, the prompt
is `/<name> <args>` and the `without` arm needs a `baseline_prompt`.
