#!/usr/bin/env python3
"""Run omp trials of one skill, rule or command, each arm isolated from the others.

  run       run each eval of an eval set under each arm in a throwaway copy of its fixture
  triggers  measure whether trigger queries make the agent load the target
  rules     check a triggered rule's offline cases with `omp ttsr test` (no model calls)
  hint      print the line the model sees for a skill

Arms: `with` (the working copy of the target, frozen when the invocation starts),
`without` (the target removed), `old=<git-rev>` (the target at that revision).

--budget is the total in USD for every paid run whose --out shares a parent directory
(`.workspaces/<name>/`): spend is kept in `<parent>/spend.jsonl` across invocations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

AGENT_DIR = Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".omp/agent")
FOREIGN_SKILL_DIRS = (".omp/skills", ".agents/skills", ".agent/skills", ".claude/skills", ".codex/skills", ".github/skills")
FRONTMATTER_NAME = re.compile(r"\A---\n(?:.*\n)*?name:\s*['\"]?([\w.-]+)['\"]?\s*\n(?:.*\n)*?---", re.MULTILINE)
TRIGGER_KEYS = re.compile(r"^(condition|astCondition|question|ttsr_trigger):", re.MULTILINE)
LOAD = re.compile(r"(skill|rule)://([^/:?#\s\"']+)")
CACHE_DIRS = {"__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache", ".git"}
MIN_RUN_BUDGET = 0.05  # USD; below this a run cannot get past its first request


# ---- target and arms ------------------------------------------------------


def target_kind(path: Path) -> tuple[str, str]:
    """(kind, name) of a skill directory or SKILL.md, a rules/*.md file or a commands/*.md file."""
    if path.name == "SKILL.md":
        path = path.parent
    if (path / "SKILL.md").is_file():
        match = FRONTMATTER_NAME.match((path / "SKILL.md").read_text())
        return "skill", match.group(1) if match else path.name
    if path.suffix in (".md", ".mdc") and path.parent.name in ("rules", "commands"):
        return ("rule" if path.parent.name == "rules" else "command"), path.stem
    sys.exit(f"{path}: not a skill directory, rules/*.md or commands/*.md")


def frontmatter(text: str) -> str:
    return text.split("\n---", 1)[0] if text.startswith("---") else ""


def is_triggered_rule(rule: Path) -> bool:
    """A rule with condition, astCondition or question: injected on a match, not listed or read."""
    return bool(TRIGGER_KEYS.search(frontmatter(rule.read_text())))


def arm_source(arm: str, target: Path, arms_dir: Path) -> Path | None:
    """A frozen copy of the guidance an arm installs, or None for `without`."""
    if arm == "without":
        return None
    real = target.resolve()
    if arm == "with":
        dest = arms_dir / "with" / real.name
        shutil.rmtree(dest.parent, ignore_errors=True)
        dest.parent.mkdir(parents=True)
        if real.is_dir():
            shutil.copytree(real, dest, symlinks=True, ignore=shutil.ignore_patterns(*CACHE_DIRS))
        else:
            shutil.copy(real, dest)
        return dest
    if arm.startswith("old="):
        rev = arm[4:]
        top = Path(git(real.parent if real.is_file() else real, "rev-parse", "--show-toplevel").strip())
        rel = real.relative_to(top)
        dest = arms_dir / f"old-{re.sub(r'[^\w.-]', '_', rev)}"
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        archive = subprocess.run(["git", "-C", str(top), "archive", rev, str(rel)], capture_output=True, check=False)
        if archive.returncode != 0:
            sys.exit(f"{rel} is not in {rev}: {archive.stderr.decode().strip()}")
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
        return dest / rel
    sys.exit(f"unknown arm {arm!r}: use with, without or old=<git-rev>")


def install(kind: str, name: str, source: Path | None, work: Path, arm_dir: Path, user_skills: Path, base: dict,
            hide_skills: tuple[str, ...] = (), hide_rules: tuple[str, ...] = ()) -> dict:
    """Install one arm's guidance for a trial in `work`; return the settings overlay it needs.

    `base` holds the user's effective `customDirectories`, `disabledExtensions` and
    `disabledRules`: overlay arrays replace the lower layer, so the overlay repeats them.
    `hide_skills` and `hide_rules` name user guidance to remove besides the target.
    """
    overlay: dict[str, Any] = {}
    disabled = list(base.get("disabledExtensions", []))
    disabled_rules = list(base.get("disabledRules", [])) + list(hide_rules)
    if kind == "skill":
        mirror = arm_dir / "skills"
        shutil.rmtree(mirror, ignore_errors=True)
        mirror.mkdir(parents=True)
        for entry in sorted(user_skills.iterdir()) if user_skills.is_dir() else []:
            if entry.name != name and entry.name not in hide_skills and (entry / "SKILL.md").exists():
                (mirror / entry.name).symlink_to(entry.resolve())
        if source is not None:
            shutil.copytree(source if source.is_dir() else source.parent, mirror / name, symlinks=True)
        else:
            disabled.append(f"skill:{name}")
        for rel in FOREIGN_SKILL_DIRS:
            shutil.rmtree(work / rel / name, ignore_errors=True)
        overlay["skills"] = {"enablePiUser": False, "customDirectories": [str(mirror), *base.get("customDirectories", [])]}
    elif kind == "rule":
        rules = work / ".omp/rules"
        (rules / f"{name}.mdc").unlink(missing_ok=True)
        if source is not None:
            rules.mkdir(parents=True, exist_ok=True)
            (rules / f"{name}.md").write_text(source.read_text())
        else:
            (rules / f"{name}.md").unlink(missing_ok=True)
            disabled_rules.append(name)
    elif kind == "command":
        dest = work / ".omp/commands" / f"{name}.md"
        if source is not None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(source.read_text())
        else:
            dest.unlink(missing_ok=True)
            disabled.append(f"slash-command:{name}")
    if disabled != base.get("disabledExtensions", []):
        overlay["disabledExtensions"] = disabled
    if disabled_rules != base.get("disabledRules", []):
        overlay["ttsr"] = {"disabledRules": disabled_rules}
    disable_mcp(work, base.get("mcpServers", []))
    return overlay


def trial_overlay(arm_overlay: dict, advisor: bool) -> dict:
    """Settings every trial runs with: no memory, session history, model switches, desktop control or advisor."""
    overlay = {"memory": {"backend": "off"}, "retry": {"modelFallback": False, "usageAwareFallback": False},
               "computer": {"enabled": False}, "archive": {"enabled": False}, **arm_overlay}
    if not advisor:
        overlay["advisor"] = {"enabled": False}
    return overlay


def effective_base() -> dict:
    """The user's effective array settings that arm overlays must repeat, and the user's MCP server names."""
    base: dict[str, list[str]] = {}
    for key, setting in (("customDirectories", "skills.customDirectories"), ("disabledExtensions", "disabledExtensions"),
                         ("disabledRules", "ttsr.disabledRules")):
        out = subprocess.run(["omp", "config", "get", setting, "--json"], capture_output=True, text=True, check=True).stdout
        base[key] = json.loads(out).get("value") or []
    mcp = AGENT_DIR / "mcp.json"
    base["mcpServers"] = sorted((json.loads(mcp.read_text()).get("mcpServers") or {}) if mcp.exists() else {})
    return base


def disable_mcp(work: Path, servers: list[str]) -> None:
    """Turn the user's MCP servers off in the trial copy: unattended yolo agents must not reach real accounts.

    A project `.omp/mcp.json` entry with `enabled: false` suppresses the same-named user server.
    """
    if not servers:
        return
    path = work / ".omp/mcp.json"
    config = json.loads(path.read_text()) if path.exists() else {}
    entries = config.setdefault("mcpServers", {})
    for server in servers:
        entries[server] = {**entries.get(server, {}), "enabled": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))


def references(name: str, target: Path, agent_dir: Path) -> list[Path]:
    """User-level guidance outside the target that links to it (skill:// or rule://)."""
    pattern = re.compile(rf"(skill|rule)://{re.escape(name)}(?![\w-])")
    real = target.resolve()
    files = [agent_dir / "RULES.md", agent_dir / "AGENTS.md"]
    for sub in ("rules", "skills", "commands", "agents"):
        root = agent_dir / sub
        for entry in sorted(root.iterdir()) if root.is_dir() else []:
            # installed skills are often symlinked directories, which rglob does not enter
            files += sorted(entry.resolve().rglob("*.md")) if entry.is_dir() else [entry]
    found = []
    for file in files:
        resolved = file.resolve()
        if file.is_file() and real not in (resolved, *resolved.parents) and pattern.search(file.read_text()):
            found.append(file)
    return found


def owner(ref: Path, agent_dir: Path) -> tuple[str, str]:
    """(kind, name) of the user guidance a referencing file belongs to: ("skill", dir), ("rule", stem) or ("other", path)."""
    for sub, kind in (("skills", "skill"), ("rules", "rule")):
        root = agent_dir / sub
        for entry in sorted(root.iterdir()) if root.is_dir() else []:
            if kind == "skill" and entry.is_dir() and entry.resolve() in (ref.resolve(), *ref.resolve().parents):
                return "skill", entry.name
            if kind == "rule" and entry.resolve() == ref.resolve():
                return "rule", entry.stem
    return "other", str(ref)


def target_markers(kind: str, name: str, target: Path) -> re.Pattern[str]:
    """Paths in tool arguments that reach the target's files directly, around skill:// and rule://."""
    rel = {"skill": rf"skills/{re.escape(name)}(?![\w-])", "rule": rf"rules/{re.escape(name)}\.md",
           "command": rf"commands/{re.escape(name)}\.md"}[kind]
    return re.compile(rf"{rel}|{re.escape(str(target.resolve()))}")


# ---- sessions ---------------------------------------------------------------


def session_metrics(session_dir: Path, prompt: str, markers: re.Pattern[str] | None = None) -> dict:
    """Cost, tokens, tool calls, guidance loads and the final answer of a run's sessions.

    Cost covers every session file under the directory, subagents and side requests
    (model_usage) included; turns, the final answer and command expansion come from the main
    session. `touched_target` is true when a tool argument names the target's files by path.
    """
    tokens = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
    cost = 0.0
    tools: dict[str, int] = {}
    loads: dict[str, set[str]] = {"skill": set(), "rule": set()}
    pending: dict[str, tuple[str, str]] = {}  # tool call id -> (scheme, name) of a skill:// or rule:// read
    turns, final, first_user, touched = 0, "", None, False
    for file in sorted(session_dir.rglob("*.jsonl")):
        main = file.parent == session_dir
        for line in file.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:  # the last line of a session killed mid-write
                continue
            if entry.get("type") == "ttsr_injection":
                loads["rule"].update(entry.get("injectedRules") or [])
            if entry.get("type") == "model_usage":
                cost += float(((entry.get("usage") or {}).get("cost") or {}).get("total") or 0)
            message = entry.get("message") if entry.get("type") == "message" else None
            if not isinstance(message, dict):
                continue
            raw = message.get("content")
            content: list[dict] = raw if isinstance(raw, list) else []
            role = message.get("role")
            if role == "user" and main and first_user is None:
                first_user = "".join(c.get("text", "") for c in content if c.get("type") == "text")
            if role == "toolResult" and not message.get("isError") and message.get("toolCallId") in pending:
                scheme, loaded = pending.pop(message["toolCallId"])
                loads[scheme].add(loaded)
            if role != "assistant":
                continue
            usage = message.get("usage") or {}
            for key in tokens:
                tokens[key] += int(usage.get(key) or 0)
            cost += float((usage.get("cost") or {}).get("total") or 0)
            calls = [c for c in content if c.get("type") == "toolCall"]
            for c in calls:
                tools[c.get("name", "?")] = tools.get(c.get("name", "?"), 0) + 1
                args = json.dumps(c.get("arguments") or {})
                match = LOAD.match(str((c.get("arguments") or {}).get("path", "")))
                if match:
                    pending[c.get("id", "")] = (match.group(1), match.group(2))
                if markers is not None and markers.search(args):
                    touched = True
            if main:
                turns += 1
                text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text").strip()
                if text and not calls:
                    final = text
    expanded = prompt.startswith("/") and first_user is not None and first_user.strip() != prompt.strip()
    return {
        "cost": round(cost, 6),
        "tokens": tokens,
        "tool_calls": tools,
        "turns": turns,
        "loads": {"skills": sorted(loads["skill"]), "rules": sorted(loads["rule"]), "command_expanded": expanded},
        "touched_target": touched,
        "final": final,
    }


# ---- skill routing hint -----------------------------------------------------


def preview(description: str) -> str:
    """omp's routing hint for a description while no compressed hint is cached (skill-descriptions.ts)."""
    text = " ".join(description.split())
    if len(text) <= 100:
        return text
    boundary = text[:99]
    sentence = re.match(r"^.*?[.!?](?=\s|$)", boundary)
    if sentence and len(sentence.group(0)) >= 40:
        return sentence.group(0)
    space = boundary.rfind(" ")
    cut = boundary[:space].rstrip() if space >= 40 else boundary
    return f"{cut}…"


def compress_prompt() -> str | None:
    """The installed omp's compress-description prompt, which keys the hint cache."""
    roots = [Path.home() / ".bun/install/global/node_modules"]
    if shutil.which("npm"):
        npm = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, check=False).stdout.strip()
        if npm:
            roots.append(Path(npm))
    for root in roots:
        candidate = root / "@oh-my-pi/pi-coding-agent/src/prompts/skills/compress-description.md"
        if candidate.is_file():
            return candidate.read_text()
    return None


def hint_cache() -> Path:
    """omp's skill-descriptions.db: in the agent dir, or under $XDG_DATA_HOME/omp when that exists."""
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg and (Path(xdg) / "omp/skill-descriptions.db").exists():
        return Path(xdg) / "omp/skill-descriptions.db"
    return AGENT_DIR / "skill-descriptions.db"


def skill_hint(skill_md: Path) -> tuple[str, str]:
    """(line the model sees, where it comes from) for a SKILL.md."""
    text = skill_md.read_text()
    front = frontmatter(text)
    name_match = FRONTMATTER_NAME.match(text)
    name = name_match.group(1) if name_match else skill_md.parent.name
    description = parse_description(front)
    if re.search(r"^(disable-model-invocation|hide):\s*true\s*$", front, re.MULTILINE):
        return preview(description), "hidden: not listed to the model; reached by /skill: or skill://"
    if len(" ".join(description.split())) <= 100:
        return preview(description), "verbatim (100 characters or fewer)"
    prompt, db = compress_prompt(), hint_cache()
    if prompt is not None and db.exists():
        key = hashlib.sha256(f"{prompt}\0{name}\0{description}".encode()).hexdigest()
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT description FROM skill_descriptions WHERE key = ?", (key,)).fetchone()
        finally:
            conn.close()
        if row:
            return row[0], "compressed hint from the cache"
    return preview(description), "preview: no compressed hint cached yet; the next session compresses it"


def parse_description(front: str) -> str:
    """The `description` of YAML frontmatter, plain or block scalar (enough for SKILL.md files)."""
    lines = front.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("description:"):
            value = line[len("description:"):].strip()
            if value in (">-", ">", "|", "|-"):
                block = []
                for nxt in lines[i + 1:]:
                    if nxt and not nxt.startswith((" ", "\t")):
                        break
                    block.append(nxt.strip())
                return (" " if value.startswith(">") else "\n").join(b for b in block if b)
            return value.strip("'\"")
    return ""


def ttsr_verdict(result: dict) -> str:
    """fires, quiet, or question (a judged rule whose prefilter matched; the CLI never judges)."""
    if result.get("triggered"):
        return "fires"
    for rule in result.get("notTriggered", []):
        if rule.get("question"):
            matched, defined = rule.get("matched") or {}, rule.get("defined") or {}
            prefilter = defined.get("regex") or defined.get("ast")
            return "question" if not prefilter or matched.get("regex") or matched.get("ast") else "quiet"
    return "quiet"


# ---- working copies and guard ----------------------------------------------------


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


def prepare_work(fixture: Path | None, setup: str | None, repo: str | None = None, rev: str | None = None) -> tuple[Path, str]:
    """A throwaway git repository outside $HOME holding the fixture; returns (path, base commit).

    A `repo` fixture is a real repository on this machine: only its tracked files at `rev`
    (default HEAD) are copied, so untracked secrets and build output stay out of the trial.
    """
    root = Path(tempfile.mkdtemp(prefix="omp-trial-", dir="/tmp"))
    work = root / "project"
    if repo is not None:
        work.mkdir()
        archive = subprocess.run(["git", "-C", str(Path(repo).expanduser()), "archive", rev or "HEAD"], capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", str(work)], input=archive.stdout, check=True)
    elif fixture is not None:
        shutil.copytree(fixture, work, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    else:
        work.mkdir()
    if setup:
        subprocess.run(setup, shell=True, cwd=work, check=True)
    git(work, "init", "-q")
    return work, commit_all(work, "fixture")


def commit_all(work: Path, message: str) -> str:
    """Commit everything in the trial copy; returns the commit later changes are diffed against."""
    git(work, "add", "-A")
    git(work, "-c", "user.email=trial@omp", "-c", "user.name=trial", "commit", "-q", "--allow-empty", "-m", message)
    return git(work, "rev-parse", "HEAD").strip()


def changes(work: Path, base: str) -> str:
    """What the agent changed since `base`, new files included."""
    git(work, "add", "-A")
    return git(work, "diff", "--cached", base)


def guard_snapshot(paths: list[Path]) -> dict[str, str]:
    """A fingerprint of everything under the guarded paths: git repos by content, other dirs by mtime and size."""
    snap: dict[str, str] = {}
    for root in paths:
        root = root.resolve()
        if (root / ".git").exists():
            diff = subprocess.run(["git", "-C", str(root), "diff", "HEAD", "--binary"], capture_output=True, check=True).stdout
            snap[f"git-diff:{root}"] = hashlib.sha256(diff).hexdigest()
            untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
            for rel in untracked:
                st = (root / rel).stat()
                snap[f"{root}/{rel}"] = f"{st.st_mtime_ns}:{st.st_size}"
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=True) if root.is_dir() else []:
            dirnames[:] = [d for d in dirnames if d not in CACHE_DIRS]
            for filename in filenames:
                st = (Path(dirpath) / filename).stat()
                snap[f"{dirpath}/{filename}"] = f"{st.st_mtime_ns}:{st.st_size}"
    return snap


def duration_seconds(text: str) -> int:
    match = re.fullmatch(r"(\d+)([smh]?)", text.strip())
    if not match:
        sys.exit(f"bad duration {text!r}: use e.g. 600, 15m or 1h")
    return int(match.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[match.group(2)]


# ---- runner -------------------------------------------------------------------


class Runner:
    """Starts paid omp sessions within the budget and stops every later one once something goes wrong."""

    def __init__(self, args: argparse.Namespace, out: Path) -> None:
        self.args = args
        self.out = out
        self.spent = 0.0
        self.reserved = 0.0
        self.lock = threading.Lock()
        self.stopped = ""
        self.ledger = out.parent / "spend.jsonl"
        self.spent_before = self.ledger_total()
        self.guarded = [AGENT_DIR / "skills", AGENT_DIR / "rules", AGENT_DIR / "commands"]
        top = subprocess.run(["git", "-C", str(args.target.resolve().parent), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=False).stdout.strip()  # a target outside git has no repo to guard
        if top:
            self.guarded.append(Path(top))
        self.before = guard_snapshot(self.guarded)

    def ledger_total(self) -> float:
        """Spend of every run under the ledger's directory, other invocations included."""
        if not self.ledger.exists():
            return 0.0
        return sum(json.loads(line)["cost"] for line in self.ledger.read_text().splitlines() if line.strip())

    def admit(self) -> float | None:
        """Reserve budget for one run and return its cost cap, or None when no run may start."""
        with self.lock:
            if self.stopped:
                return None
            remaining = self.args.budget - self.ledger_total() - self.reserved
            if remaining < MIN_RUN_BUDGET:
                self.stopped = (f"the approved budget of ${self.args.budget:.2f} is spent or reserved "
                                f"(${self.ledger_total():.2f} spent); ask the user before spending more")
                return None
            cap = round(min(self.args.max_cost, remaining), 2)
            self.reserved += cap
            return cap

    def stop(self, reason: str) -> None:
        with self.lock:
            self.stopped = self.stopped or reason

    def charge(self, cost: float, cap: float) -> None:
        """Record a finished run's cost and release its reservation; stop if files outside the trial changed."""
        with self.lock:
            self.spent += cost
            self.reserved -= cap
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger.open("a") as ledger:
                ledger.write(json.dumps({"out": self.out.name, "cost": cost, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
        after = guard_snapshot(self.guarded)
        changed = sorted(k for k in set(self.before) | set(after) if self.before.get(k) != after.get(k))
        if changed:
            self.stop("files outside the trial changed: " + ", ".join(changed[:5]))

    def omp(self, prompt: str, work: Path, overlay: Path, session: Path, max_time: str, cap: float) -> subprocess.Popen:
        cmd = ["omp", "-p", "--mode", "json", "--no-title", "--approval-mode", "yolo", "--session-dir", str(session),
               "--max-time", max_time, "--max-cost", str(cap)]
        if self.args.model:
            cmd += ["--model", self.args.model]
        if self.args.thinking:
            cmd += ["--thinking", self.args.thinking]
        return subprocess.Popen([*cmd, "--", prompt], cwd=work, env=trial_env(overlay), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def budget_line(self) -> str:
        return f"budget ${self.args.budget:.2f} in total, ${self.spent_before:.2f} spent before"

    def finish(self) -> None:
        """Print the spend; exit 1 when the invocation stopped early, so callers and loops stop too."""
        print(f"spent ${self.spent:.2f} now, ${self.ledger_total():.2f} of ${self.args.budget:.2f} in total"
              + (f"; stopped: {self.stopped}" if self.stopped else ""))
        if self.stopped:
            sys.exit(1)


def trial_env(overlay: Path) -> dict[str, str]:
    """Environment of a trial session: the arm's overlay last, and the marker that refuses nested paid trials."""
    files = os.pathsep.join(filter(None, [os.environ.get("PI_CONFIG_FILES"), str(overlay)]))
    return {**os.environ, "PI_CONFIG_FILES": files, "OMP_TRIAL": "1"}


class Plan:
    """What one invocation installs: the target, its frozen arm sources, and what the without arm also hides."""

    def __init__(self, args: argparse.Namespace, arms: list[str]) -> None:
        self.kind, self.name = target_kind(args.target)
        self.sources = {arm: arm_source(arm, args.target, args.out / "arms") for arm in arms}
        self.base = effective_base()
        self.markers = target_markers(self.kind, self.name, args.target)
        self.references = references(self.name, args.target, AGENT_DIR)
        owned = [owner(p, AGENT_DIR) for p in self.references] if getattr(args, "hide_references", False) else []
        self.hide_skills = tuple(sorted({n for k, n in owned if k == "skill"}))
        self.hide_rules = tuple(sorted({n for k, n in owned if k == "rule"}))
        for ref in self.references:
            kind, owned_name = owner(ref, AGENT_DIR)
            hidden = owned_name in (self.hide_skills if kind == "skill" else self.hide_rules if kind == "rule" else ())
            print(f"note: {ref} links to {self.name}; " + ("hidden in the without arm" if hidden else "installed in every arm"))

    def setup(self, arm: str, work: Path, run_dir: Path, advisor: bool) -> Path:
        hide = arm == "without"
        arm_overlay = install(self.kind, self.name, self.sources[arm], work, run_dir / "arm", AGENT_DIR / "skills", self.base,
                              self.hide_skills if hide else (), self.hide_rules if hide else ())
        path = run_dir / "overlay.json"
        path.write_text(json.dumps(trial_overlay(arm_overlay, advisor), indent=2))
        return path

    def preflight(self, arm: str, work: Path, overlay: Path, run_dir: Path) -> str | None:
        """None when the arm loads exactly the guidance it should, else the problem."""
        env = trial_env(overlay)
        source = self.sources[arm]
        if self.kind == "skill":
            out = subprocess.run(["omp", "skill", "list", "--json"], cwd=work, env=env, capture_output=True, text=True, check=True).stdout
            found = [s["filePath"] for s in json.loads(out).get("skills", []) if s["name"] == self.name or s["name"].endswith(f"/{self.name}")]
            want = [] if source is None else [str(run_dir / "arm/skills" / self.name / "SKILL.md")]
            return None if found == want else f"skill {self.name}: loads {found or 'nothing'}, expected {want or 'nothing'}"
        if self.kind == "rule":
            out = subprocess.run(["omp", "ttsr", "list", "--json"], cwd=work, env=env, capture_output=True, text=True, check=True).stdout
            found = [r["path"] for r in json.loads(out or "[]") if r["name"] == self.name]
            mine = str(work / ".omp/rules" / f"{self.name}.md")
            want = [mine] if source is not None and is_triggered_rule(source) else []
            return None if found == want else f"rule {self.name}: registered {found or 'nothing'}, expected {want or 'nothing'}"
        return None


def run_one(runner: Runner, plan: Plan, ev: dict, ev_root: Path, arm: str, rep: int) -> dict:
    args = runner.args
    run_dir = runner.out / "runs" / ev["id"] / f"{arm.replace('=', '-')}-{rep}"
    meta = {"eval": ev["id"], "arm": arm, "rep": rep}
    cap = 0.0
    if not args.dry_run:
        admitted = runner.admit()
        if admitted is None:
            return {**meta, "status": f"skipped: {runner.stopped}"}
        cap = admitted
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    fixture = ev.get("fixture")
    work, _ = prepare_work((ev_root / fixture) if fixture else None, ev.get("setup"), ev.get("repo"), ev.get("rev"))
    cost = 0.0
    try:
        overlay = plan.setup(arm, work, run_dir, args.advisor)
        problem = plan.preflight(arm, work, overlay, run_dir)
        if problem:
            runner.stop(f"isolation failed ({arm}): {problem}")
            return {**meta, "status": f"error: {problem}"}
        if args.dry_run:
            print(f"{ev['id']} {arm}: isolation ok")
            return {**meta, "status": "dry run"}
        base_commit = commit_all(work, "arm")
        prompt = ev["baseline_prompt"] if arm == "without" and plan.kind == "command" else ev["prompt"]
        max_time = ev.get("max_time", args.max_time)
        start = time.time()
        proc = runner.omp(prompt, work, overlay, run_dir / "session", max_time, cap)
        try:
            stdout, stderr = proc.communicate(timeout=duration_seconds(max_time) + 300)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            stderr += "\n[trial.py: killed after --max-time plus 5 minutes]"
        (run_dir / "events.jsonl").write_text(stdout)
        (run_dir / "stderr.txt").write_text(stderr[-20000:])
        metrics = session_metrics(run_dir / "session", prompt, plan.markers)
        cost = metrics["cost"]
        (run_dir / "final.md").write_text(metrics.pop("final"))
        (run_dir / "diff.patch").write_text(changes(work, base_commit)[:400_000])
        checks = []
        for check in ev.get("checks", []):
            try:
                res = subprocess.run(check["run"], shell=True, cwd=work, capture_output=True, text=True, check=False,
                                     timeout=check.get("timeout", 600))
                checks.append({"name": check["name"], "passed": res.returncode == 0, "exit_code": res.returncode,
                               "output": (res.stdout + res.stderr)[-3000:]})
            except subprocess.TimeoutExpired:
                checks.append({"name": check["name"], "passed": False, "exit_code": None, "output": "timed out"})
        (run_dir / "checks.json").write_text(json.dumps(checks, indent=2))
        metrics = {**meta, "prompt": prompt, "exit_code": proc.returncode, "seconds": round(time.time() - start, 1), **metrics}
        (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
        passed = sum(c["passed"] for c in checks)
        print(f"{ev['id']} {arm} #{rep}: exit {proc.returncode}, ${cost:.2f}, {metrics['seconds']}s, checks {passed}/{len(checks)}"
              + (", touched the target's files" if metrics["touched_target"] else ""), flush=True)
        return {**meta, "status": "done", "dir": str(run_dir.relative_to(runner.out))}
    finally:
        if not args.dry_run:
            runner.charge(cost, cap)
        if not args.keep:
            shutil.rmtree(work.parent, ignore_errors=True)


# ---- commands -----------------------------------------------------------------


def load_evals(path: Path) -> dict:
    data = json.loads(path.read_text())
    ids = [e["id"] for e in data.get("evals", [])]
    if len(ids) != len(set(ids)):
        sys.exit("eval ids must be unique")
    for item in [*data.get("evals", []), *data.get("triggers", [])]:
        for key in ("fixture", "setup", "repo", "rev"):
            item.setdefault(key, data.get(key))
    return data


def prepare_args(args: argparse.Namespace) -> None:
    """Absolute paths (trials run elsewhere and overlays name them); refuse paid trials inside a trial."""
    for key in ("target", "evals", "out"):
        setattr(args, key, getattr(args, key).resolve())
    if os.environ.get("OMP_TRIAL") and not getattr(args, "dry_run", False):
        sys.exit("this session is itself a trial: paid trials inside it are refused; use --dry-run or report the plan")


def cmd_run(args: argparse.Namespace) -> None:
    prepare_args(args)
    data = load_evals(args.evals)
    evals = [e for e in data["evals"] if not args.eval or e["id"] in args.eval][: args.limit or None]
    arms = args.arm or ["without", "with"]
    args.out.mkdir(parents=True, exist_ok=True)
    plan = Plan(args, arms)
    if plan.kind == "command" and "without" in arms and any(not e.get("baseline_prompt") for e in evals):
        sys.exit("a command's without arm needs a baseline_prompt in every eval")
    runner = Runner(args, args.out)
    jobs = [(e, arm, rep) for e in evals for rep in range(1, args.reps + 1) for arm in arms]
    print(f"{plan.kind} {plan.name}: {len(evals)} evals x {len(arms)} arms x {args.reps} reps = {len(jobs)} runs; {runner.budget_line()}")
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda j: run_one(runner, plan, j[0], args.evals.parent, j[1], j[2]), jobs))
    index = {"target": str(args.target), "kind": plan.kind, "name": plan.name, "arms": arms, "model": args.model,
             "references": [str(p) for p in plan.references], "hidden_in_without": [*plan.hide_skills, *plan.hide_rules],
             "evals": {e["id"]: {k: e.get(k) for k in ("prompt", "baseline_prompt", "expectations")} for e in evals},
             "runs": results, "spent": round(runner.spent, 4), "stopped": runner.stopped}
    (args.out / "index.json").write_text(json.dumps(index, indent=2))
    for arm in arms:
        checks = [c["passed"] for r in results if r["arm"] == arm and r["status"] == "done"
                  for c in json.loads((args.out / r["dir"] / "checks.json").read_text())]
        if checks:
            print(f"METRIC checks_{re.sub(r'[^\w]', '_', arm)}={sum(checks) / len(checks):.4f}")
    if not args.dry_run:
        runner.finish()


def cmd_triggers(args: argparse.Namespace) -> None:
    prepare_args(args)
    kind, name = target_kind(args.target)
    if kind == "command":
        sys.exit("commands are started by the user; they have no trigger to test")
    if kind == "rule" and is_triggered_rule(args.target):
        sys.exit("a triggered rule is injected on a match, not chosen by the agent: test it with `rules`")
    data = load_evals(args.evals)
    queries = [q for q in data.get("triggers", []) if args.split == "all" or q.get("split", "train") == args.split]
    if not queries:
        sys.exit(f"no trigger queries for split {args.split}")
    if kind == "skill":
        hint, origin = skill_hint(args.target if args.target.name == "SKILL.md" else args.target / "SKILL.md")
        print(f"hint: {hint}  [{origin}]")
    args.out.mkdir(parents=True, exist_ok=True)
    plan = Plan(args, [args.arm])
    runner = Runner(args, args.out)

    def probe(job: tuple[int, dict, int]) -> dict:
        i, q, rep = job
        cap = runner.admit()
        if cap is None:
            return {"query": i, "rep": rep, "status": f"skipped: {runner.stopped}"}
        run_dir = args.out / "triggers" / args.split / f"q{i}-{rep}"
        shutil.rmtree(run_dir, ignore_errors=True)
        run_dir.mkdir(parents=True)
        work, _ = prepare_work((args.evals.parent / q["fixture"]) if q.get("fixture") else None, q.get("setup"), q.get("repo"), q.get("rev"))
        cost = 0.0
        try:
            overlay = plan.setup(args.arm, work, run_dir, args.advisor)
            problem = plan.preflight(args.arm, work, overlay, run_dir)
            if problem:
                runner.stop(f"isolation failed: {problem}")
                return {"query": i, "rep": rep, "status": f"error: {problem}"}
            proc = runner.omp(q["query"], work, overlay, run_dir / "session", args.max_time, cap)
            triggered, calls, loaded = False, 0, []
            assert proc.stdout is not None
            for line in proc.stdout:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:  # stdout lines that are not events, e.g. a crash trace
                    continue
                message = event.get("message") or {}
                if event.get("type") != "message_end" or message.get("role") != "assistant":
                    continue
                for c in message.get("content") or []:
                    if c.get("type") != "toolCall":
                        continue
                    calls += 1
                    match = LOAD.match(str((c.get("arguments") or {}).get("path", "")))
                    if match and match.group(1) == "skill" and match.group(2) not in loaded:
                        loaded.append(match.group(2))
                    triggered = triggered or bool(match and match.group(2) == name)
                if triggered or calls >= args.max_tool_calls:
                    break
            proc.kill()
            proc.wait()
            cost = session_metrics(run_dir / "session", q["query"])["cost"]
            return {"query": i, "rep": rep, "status": "done", "triggered": triggered, "loaded": loaded, "cost": cost}
        finally:
            runner.charge(cost, cap)
            shutil.rmtree(work.parent, ignore_errors=True)

    jobs = [(i, q, rep) for i, q in enumerate(queries) for rep in range(1, args.reps + 1)]
    print(f"{len(queries)} queries x {args.reps} reps = {len(jobs)} runs ({args.split}); {runner.budget_line()}")
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(probe, jobs))
    rows, correct = [], 0
    for i, q in enumerate(queries):
        done = [r for r in results if r["query"] == i and r["status"] == "done"]
        rate = sum(r["triggered"] for r in done) / len(done) if done else None
        ok = rate is not None and (rate >= 0.5) == bool(q["should_trigger"])
        correct += ok
        orders = [" > ".join(r["loaded"]) or "none" for r in done]
        rows.append({"query": q["query"], "should_trigger": q["should_trigger"], "rate": rate, "runs": len(done), "correct": ok,
                     "loaded": orders})
        print(f"{'ok  ' if ok else 'MISS'} {'-' if rate is None else f'{rate:.2f}'} should={q['should_trigger']}: {q['query'][:90]}"
              + ("" if ok else f"\n     skills loaded, in order: {' | '.join(orders)}"))
    accuracy = correct / len(queries)
    (args.out / f"triggers-{args.split}.json").write_text(json.dumps({"target": name, "split": args.split, "accuracy": accuracy,
                                                                      "queries": rows, "spent": runner.spent}, indent=2))
    print(f"METRIC trigger_accuracy_{args.split}={accuracy:.4f}")
    runner.finish()


def cmd_rules(args: argparse.Namespace) -> None:
    kind, _ = target_kind(args.target)
    if kind != "rule":
        sys.exit("rules needs a rules/*.md target")
    cases = load_evals(args.evals).get("rule_cases", [])
    if not cases:
        sys.exit("the eval set has no rule_cases")
    failed = 0
    for case in cases:
        source = case.get("source", "tool")
        cmd = ["omp", "ttsr", "test", "--rule", str(args.target.resolve()), "--source", source, "--json", "--file", "-"]
        if source == "tool":
            cmd += ["--tool", case.get("tool", "edit")]
        if case.get("path"):
            cmd += ["--path", case["path"]]
        if case.get("agent"):
            cmd += ["--agent", case["agent"]]
        out = subprocess.run(cmd, input=case["snippet"], capture_output=True, text=True, check=True, cwd=tempfile.gettempdir())
        verdict = ttsr_verdict(json.loads(out.stdout))
        want = "fires" if case["fires"] else "quiet"
        if verdict == "question":
            status = "prefilter matched; the judge decides (not run offline)"
            failed += not case["fires"]
        else:
            status = "ok" if verdict == want else "FAIL"
            failed += status == "FAIL"
        print(f"{status}: expected {want}, got {verdict}: {case.get('path', source)} {case['snippet'][:60]!r}")
    sys.exit(1 if failed else 0)


def cmd_hint(args: argparse.Namespace) -> None:
    kind, _ = target_kind(args.target)
    if kind != "skill":
        sys.exit("hint needs a skill; rule descriptions are listed verbatim")
    hint, origin = skill_hint(args.target if args.target.name == "SKILL.md" else args.target / "SKILL.md")
    print(f"{hint}\n[{origin}; {len(hint)} characters]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--target", type=Path, required=True, help="skill dir, rules/<name>.md or commands/<name>.md")
    for name, helptext in (("run", "run evals under each arm"), ("triggers", "measure loading on trigger queries")):
        p = sub.add_parser(name, parents=[common], help=helptext)
        p.add_argument("--evals", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True, help="iteration directory, e.g. .workspaces/<name>/iteration-1")
        p.add_argument("--budget", type=float, required=True, help="total USD for all runs sharing --out's parent")
        p.add_argument("--model")
        p.add_argument("--thinking")
        p.add_argument("--jobs", type=int, default=4)
        p.add_argument("--advisor", action="store_true", help="keep the advisor on, as in the user's sessions")
        p.add_argument("--hide-references", action="store_true",
                       help="in the without arm, also hide user skills and rules that link to the target")
    run = sub.choices["run"]
    run.add_argument("--arm", action="append", help="with, without, old=<git-rev>; repeatable (default: without, with)")
    run.add_argument("--reps", type=int, default=3)
    run.add_argument("--eval", action="append", help="run only this eval id; repeatable")
    run.add_argument("--limit", type=int, help="run only the first N evals")
    run.add_argument("--max-cost", type=float, default=3.0, help="USD cap per session")
    run.add_argument("--max-time", default="20m")
    run.add_argument("--dry-run", action="store_true", help="install each arm and check its isolation; no model calls")
    run.add_argument("--keep", action="store_true", help="keep the trial working copies under /tmp")
    trig = sub.choices["triggers"]
    trig.add_argument("--arm", default="with")
    trig.add_argument("--reps", type=int, default=3)
    trig.add_argument("--split", choices=["train", "test", "all"], default="train")
    trig.add_argument("--max-tool-calls", type=int, default=4, help="not triggered after this many other tool calls")
    trig.add_argument("--max-cost", type=float, default=1.0, help="USD cap per session")
    trig.add_argument("--max-time", default="5m")
    rules = sub.add_parser("rules", parents=[common], help="offline cases of a triggered rule")
    rules.add_argument("--evals", type=Path, required=True)
    sub.add_parser("hint", parents=[common], help="the line the model sees for a skill")
    args = parser.parse_args()
    {"run": cmd_run, "triggers": cmd_triggers, "rules": cmd_rules, "hint": cmd_hint}[args.cmd](args)


if __name__ == "__main__":
    main()
