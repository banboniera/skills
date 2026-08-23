# `skills`

CLI for managing agent skills.

## Global options

- `--help`, `-h`: Show help.
- `--version`, `-v`: Show version.

## Commands

### `skills add <package>`

Add a skill package. Alias: `skills a`.

Options:

- `-g`, `--global`: Install globally instead of project-level.
- `-a`, `--agent <agents>`: Install to specific agents. Use `*` for all agents.
- `-s`, `--skill <skills>`: Install specific skills. Use `*` for all skills.
- `-l`, `--list`: List available skills without installing.
- `-y`, `--yes`: Skip confirmation prompts.
- `--copy`: Copy files instead of symlinking.
- `--subagent <names>`: Install to Eve subagents. Use `root` for the root agent.
- `--all`: Shorthand for `--skill '*' --agent '*' -y`.
- `--full-depth`: Search all subdirectories even when a root `SKILL.md` exists.

### `skills use <source>[@<skill>]`

Generate a prompt for one skill without installing it.

Options:

- `-s`, `--skill <skill>`: Select the skill to use.
- `-a`, `--agent <agent>`: Start a supported agent interactively.
- `--full-depth`: Search all subdirectories even when a root `SKILL.md` exists.
- `--dangerously-accept-openclaw-risks`: Allow unverified OpenClaw community skills.

### `skills remove [skills...]`

Remove installed skills. Alias: `skills rm`.

Options:

- `-g`, `--global`: Remove from global scope.
- `-a`, `--agent <agents>`: Remove from specific agents. Use `*` for all agents.
- `-s`, `--skill <skills>`: Remove specific skills. Use `*` for all skills.
- `-y`, `--yes`: Skip confirmation prompts.
- `--all`: Shorthand for `--skill '*' --agent '*' -y`.

### `skills list`

List installed skills. Alias: `skills ls`.

Options:

- `-g`, `--global`: List global skills.
- `-a`, `--agent <agents>`: Filter by agents.
- `--json`: Output JSON.

### `skills find [query]`

Search for skills.

Options:

- `--owner <owner>`: Search only repositories from a GitHub owner.

### `skills update [skills...]`

Update skills to latest versions. Alias: `skills upgrade`.

Options:

- `-g`, `--global`: Update global skills only.
- `-p`, `--project`: Update project skills only.
- `-y`, `--yes`: Skip scope prompt.

### `skills init [name]`

Initialize a skill. Creates `<name>/SKILL.md` or `./SKILL.md`.

### `skills experimental_install`

Restore skills from `skills-lock.json`.

### `skills experimental_sync`

Sync skills from `node_modules` into agent directories.

Options:

- `-a`, `--agent <agents>`: Install to specific agents. Use `*` for all agents.
- `-y`, `--yes`: Skip confirmation prompts.
