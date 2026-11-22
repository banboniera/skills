# omp slash commands

A command is a one-file procedure the user starts by name, with arguments.
Make it a skill instead when it needs bundled files or the agent must reach it
on its own.

`~/.omp/agent/commands/<name>.md` (user) or `.omp/commands/<name>.md`
(project, read from the session's working directory; wins on the same name).
The filename is the name.

Frontmatter: `description` (the autocomplete line), `argument-hint` (ghost
text after the name), `side: true` (in the interactive TUI, runs as a `/btw`
side question: off the transcript, without tools or steering; elsewhere it is
an ordinary prompt).

Before the model sees the body:

1. Arguments are substituted once: `$1`, `$2`, …; `$@[2]` is every argument
   from the second on, `$@[2:3]` three of them; `$ARGUMENTS` and `$@` are all
   of them. A missing argument becomes an empty string; a body without
   placeholders gets the arguments appended.
2. The result is rendered as a template: `{{…}}` is evaluated and an unclosed
   `{{` fails the command, with no escape. Keep text that contains `{{`
   (GitHub Actions, Jinja, Vue) in a file the body tells the agent to read.

Arguments split at spaces; a quote groups words only at the start of an
argument or after `=`, so apostrophes stay literal; there are no backslash
escapes, and empty quoted arguments are dropped.

The body is the procedure the session follows: the goal, steps that end on
something checkable, what to do when an argument is empty, and the report
format last.

**Checks:** every placeholder follows the rules above, and the body has no
`{{`. In trials, the prompt is `/<name> <args>` and the `without` arm needs a
`baseline_prompt`.
