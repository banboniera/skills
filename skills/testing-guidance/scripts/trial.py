#!/usr/bin/env python3
"""Run omp trials of one skill, rule or command, each arm isolated from the others.

  run       run each eval of an eval set under each arm in a throwaway copy of its fixture
  triggers  measure whether the trigger queries make the agent load the target
  rules     check a rule's offline trigger cases with `omp ttsr test` (no model calls)
  hint      print the routing hint the model sees for a skill

Arms: `with` (the working copy of the target), `without` (the target removed),
`old=<git-rev>` (the target at that revision). The eval-set format and the run
layout are in ../evals.md.
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
SHADOW = "Hides the user rule of the same name in this trial. No frontmatter, so it never loads.\n"
FOREIGN_SKILL_DIRS = (".omp/skills", ".agents/skills", ".agent/skills", ".claude/skills", ".codex/skills", ".github/skills")
FRONTMATTER_NAME = re.compile(r"\A---\n(?:.*\n)*?name:\s*['\"]?([\w.-]+)['\"]?\s*\n(?:.*\n)*?---", re.MULTILINE)


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


def arm_source(arm: str, target: Path, scratch: Path) -> Path | None:
    """The guidance an arm installs: a copy of the target, the target at a git revision, or None."""
    if arm == "without":
        return None
    if arm == "with":
        return target
    if arm.startswith("old="):
        rev = arm[4:]
        real = target.resolve()
        top = Path(git(real.parent if real.is_file() else real, "rev-parse", "--show-toplevel").strip())
        rel = real.relative_to(top)
        dest = scratch / f"old-{re.sub(r'[^\w.-]', '_', rev)}"
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        archive = subprocess.run(["git", "-C", str(top), "archive", rev, str(rel)], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
        return dest / rel
    sys.exit(f"unknown arm {arm!r}: use with, without or old=<git-rev>")


def install(kind: str, name: str, source: Path | None, work: Path, arm_dir: Path, user_skills: Path, base: dict,
            shadow_rules: list[str] | tuple[str, ...] = ()) -> dict:
    """Install one arm's guidance for a trial in `work`; return the settings overlay it needs.

    `base` holds the user's effective `customDirectories` and `disabledExtensions`: overlay arrays
    replace the lower layer, so the overlay repeats them. `shadow_rules` names user rules to hide.
    """
    overlay: dict[str, Any] = {}
    if kind == "skill":
        mirror = arm_dir / "skills"
        shutil.rmtree(mirror, ignore_errors=True)
        mirror.mkdir(parents=True)
        for entry in sorted(user_skills.iterdir()) if user_skills.is_dir() else []:
            if entry.name != name and (entry / "SKILL.md").exists():
                (mirror / entry.name).symlink_to(entry.resolve())
        if source is not None:
            shutil.copytree(source if source.is_dir() else source.parent, mirror / name, symlinks=True)
        for rel in FOREIGN_SKILL_DIRS:
            shutil.rmtree(work / rel / name, ignore_errors=True)
        overlay["skills"] = {"enablePiUser": False, "customDirectories": [str(mirror), *base.get("customDirectories", [])]}
    elif kind == "rule":
        rules = work / ".omp/rules"
        rules.mkdir(parents=True, exist_ok=True)
        (rules / f"{name}.mdc").unlink(missing_ok=True)
        (rules / f"{name}.md").write_text(source.read_text() if source else SHADOW)
    elif kind == "command":
        dest = work / ".omp/commands" / f"{name}.md"
        if source is not None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(source.read_text())
        else:
            dest.unlink(missing_ok=True)
            overlay["disabledExtensions"] = [*base.get("disabledExtensions", []), f"slash-command:{name}"]
    for rule in shadow_rules:
        (work / ".omp/rules").mkdir(parents=True, exist_ok=True)
        (work / ".omp/rules" / f"{rule}.md").write_text(SHADOW)
    return overlay


def trial_overlay(arm_overlay: dict, advisor: bool) -> dict:
    """Settings every trial runs with: no memory writes, no silent model switches, no advisor notes."""
    overlay = {"memory": {"backend": "off"}, "retry": {"modelFallback": False, "usageAwareFallback": False}, **arm_overlay}
    if not advisor:
        overlay["advisor"] = {"enabled": False}
    return overlay


def effective_base() -> dict:
    """The user's effective array settings that arm overlays must repeat."""
    base = {}
    for key, setting in (("customDirectories", "skills.customDirectories"), ("disabledExtensions", "disabledExtensions")):
        out = subprocess.run(["omp", "config", "get", setting, "--json"], capture_output=True, text=True, check=True).stdout
        base[key] = json.loads(out).get("value") or []
    return base


# ---- sessions ---------------------------------------------------------------


def session_metrics(session_dir: Path, prompt: str) -> dict:
    """Cost, tokens, tool calls, guidance loads and the final answer of a run's sessions.

    Cost and tokens cover every session file under the directory, subagents included; turns, the
    final answer and command expansion come from the main session (the top-level file).
    """
    tokens = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
    cost = 0.0
    tools: dict[str, int] = {}
    loads: dict[str, set[str]] = {"skill": set(), "rule": set()}
    pending: dict[str, tuple[str, str]] = {}  # tool call id -> (scheme, name) of a skill:// or rule:// read
    turns, final, first_user = 0, "", None
    for file in sorted(session_dir.rglob("*.jsonl")):
        main = file.parent == session_dir
        for line in file.read_text().splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:  # the last line of a session killed mid-write
                continue
            if entry.get("type") == "ttsr_injection":
                loads["rule"].update(entry.get("injectedRules") or [])
            message = entry.get("message") if entry.get("type") == "message" else None
            if not isinstance(message, dict):
                continue
            raw = message.get("content")
            content: list[dict] = raw if isinstance(raw, list) else []
            role = message.get("role")
            if role == "user" and main and first_user is None:
                first_user = "".join(c.get("text", "") for c in content if c.get("type") == "text")
            if role == "toolResult" and not message.get("isError") and message.get("toolCallId") in pending:
                scheme, name = pending.pop(message["toolCallId"])
                loads[scheme].add(name)
            if role != "assistant":
                continue
            usage = message.get("usage") or {}
            for key in tokens:
                tokens[key] += int(usage.get(key) or 0)
            cost += float((usage.get("cost") or {}).get("total") or 0)
            calls = [c for c in content if c.get("type") == "toolCall"]
            for c in calls:
                tools[c.get("name", "?")] = tools.get(c.get("name", "?"), 0) + 1
                match = re.match(r"(skill|rule)://([^/:?#\s]+)", str((c.get("arguments") or {}).get("path", "")))
                if match:
                    pending[c.get("id", "")] = (match.group(1), match.group(2))
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
    has_npm = shutil.which("npm") is not None
    npm = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, check=False).stdout.strip() if has_npm else ""
    if npm:
        roots.append(Path(npm))
    for root in roots:
        candidate = root / "@oh-my-pi/pi-coding-agent/src/prompts/skills/compress-description.md"
        if candidate.is_file():
            return candidate.read_text()
    return None


def skill_hint(skill_md: Path) -> tuple[str, str]:
    """(hint the model sees, where it comes from) for a SKILL.md."""
    text = skill_md.read_text()
    front = text.split("\n---", 1)[0] if text.startswith("---") else ""
    name_match = FRONTMATTER_NAME.match(text)
    name = name_match.group(1) if name_match else skill_md.parent.name
    description = parse_description(front)
    if re.search(r"^(disable-model-invocation|hide):\s*true\s*$", front, re.MULTILINE):
        return preview(description), "hidden: not listed to the model; reached by /skill: or skill://"
    if len(" ".join(description.split())) <= 100:
        return preview(description), "verbatim (100 characters or fewer)"
    prompt = compress_prompt()
    db = AGENT_DIR / "skill-descriptions.db"
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


# ---- rules ------------------------------------------------------------------


def ttsr_verdict(result: dict) -> str:
    """fires, quiet, or question (a judged rule the CLI cannot decide)."""
    if result.get("triggered"):
        return "fires"
    if any(r.get("question") for r in result.get("notTriggered", [])):
        return "question"
    return "quiet"


def references(name: str, target: Path, agent_dir: Path) -> list[Path]:
    """User-level guidance outside the target that points at it: it stays installed in every arm."""
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


# ---- running ------------------------------------------------------------------


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


def prepare_work(fixture: Path | None, setup: str | None) -> tuple[Path, str]:
    """A throwaway git repository outside $HOME holding the fixture; returns (path, base commit)."""
    root = Path(tempfile.mkdtemp(prefix="omp-trial-", dir="/tmp"))
    work = root / "project"
    if fixture is not None:
        shutil.copytree(fixture, work, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    else:
        work.mkdir()
    if setup:
        subprocess.run(setup, shell=True, cwd=work, check=True)
    git(work, "init", "-q")
    return work, commit_all(work, "fixture")


def commit_all(work: Path, message: str) -> str:
    """Commit everything in the trial copy; returns the commit, the base later changes are diffed against."""
    git(work, "add", "-A")
    git(work, "-c", "user.email=trial@omp", "-c", "user.name=trial", "commit", "-q", "--allow-empty", "-m", message)
    return git(work, "rev-parse", "HEAD").strip()


def changes(work: Path, base: str) -> str:
    """What the agent changed since `base`, new files included."""
    git(work, "add", "-A")
    return git(work, "diff", "--cached", base)


def guard_snapshot(paths: list[Path]) -> dict[str, str]:
    """mtime and size of every file under the guarded paths, plus git status of the repositories."""
    snap: dict[str, str] = {}
    for root in paths:
        root = root.resolve()
        if (root / ".git").exists():
            status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, check=True)
            snap[f"git:{root}"] = status.stdout
            continue
        for file in root.rglob("*") if root.is_dir() else []:
            if file.is_file() and "__pycache__" not in file.parts:
                st = file.stat()
                snap[str(file)] = f"{st.st_mtime_ns}:{st.st_size}"
    return snap


class Runner:
    def __init__(self, args: argparse.Namespace, out: Path) -> None:
        self.args = args
        self.out = out
        self.spent = 0.0
        self.lock = threading.Lock()
        self.stopped = ""
        self.guarded = [AGENT_DIR / "skills", AGENT_DIR / "rules", AGENT_DIR / "commands"]
        top = subprocess.run(["git", "-C", str(args.target.resolve().parent), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=False).stdout.strip()  # a target outside git has no repo to guard
        if top:
            self.guarded.append(Path(top))
        self.before = guard_snapshot(self.guarded)

    def omp(self, prompt: str, work: Path, overlay: Path, session: Path, max_time: str) -> subprocess.Popen:
        cmd = ["omp", "-p", "--mode", "json", "--no-title", "--approval-mode", "yolo", "--session-dir", str(session),
               "--max-time", max_time, "--max-cost", str(self.args.max_cost)]
        if self.args.model:
            cmd += ["--model", self.args.model]
        if self.args.thinking:
            cmd += ["--thinking", self.args.thinking]
        env = {**os.environ, "PI_CONFIG_FILES": os.pathsep.join(filter(None, [os.environ.get("PI_CONFIG_FILES"), str(overlay)]))}
        return subprocess.Popen([*cmd, "--", prompt], cwd=work, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def admit(self) -> bool:
        with self.lock:
            if self.stopped:
                return False
            if self.spent >= self.args.budget:
                self.stopped = f"budget of ${self.args.budget} spent"
                return False
            return True

    def stop(self, reason: str) -> None:
        with self.lock:
            self.stopped = self.stopped or reason

    def charge(self, cost: float) -> None:
        with self.lock:
            self.spent += cost
        after = guard_snapshot(self.guarded)
        changed = sorted(k for k in set(self.before) | set(after) if self.before.get(k) != after.get(k))
        if changed:
            self.stop("files outside the trial changed: " + ", ".join(changed[:5]))


def setup_arm(kind: str, name: str, source: Path | None, args: argparse.Namespace, work: Path, run_dir: Path, base: dict,
              shadow_rules: list[str] | tuple[str, ...] = ()) -> Path:
    arm_overlay = install(kind, name, source, work, run_dir / "arm", AGENT_DIR / "skills", base, shadow_rules)
    overlay = trial_overlay(arm_overlay, args.advisor)
    path = run_dir / "overlay.json"
    path.write_text(json.dumps(overlay, indent=2))
    return path


def preflight(kind: str, name: str, arm: str, work: Path, overlay: Path, expected: Path) -> str | None:
    """None when the arm loads exactly the guidance it should, else the problem."""
    env = {**os.environ, "PI_CONFIG_FILES": str(overlay)}
    if kind == "skill":
        out = subprocess.run(["omp", "skill", "list", "--json"], cwd=work, env=env, capture_output=True, text=True, check=True).stdout
        found = [s["filePath"] for s in json.loads(out).get("skills", []) if s["name"] == name or s["name"].endswith(f"/{name}")]
        want = [] if arm == "without" else [str(expected / name / "SKILL.md")]
        return None if found == want else f"skill {name}: loads {found or 'nothing'}, expected {want or 'nothing'}"
    if kind == "rule":
        out = subprocess.run(["omp", "ttsr", "list", "--json"], cwd=work, env=env, capture_output=True, text=True, check=True).stdout
        found = [r["path"] for r in json.loads(out or "[]") if r["name"] == name]
        mine = str(work / ".omp/rules" / f"{name}.md")
        if any(p != mine for p in found):
            return f"rule {name}: another copy loads: {found}"
    return None


def run_one(runner: Runner, kind: str, name: str, ev: dict, ev_root: Path, arm: str, source: Path | None, rep: int, base: dict) -> dict:
    args = runner.args
    run_dir = runner.out / "runs" / ev["id"] / f"{arm.replace('=', '-')}-{rep}"
    meta = {"eval": ev["id"], "arm": arm, "rep": rep}
    if not args.dry_run and not runner.admit():
        return {**meta, "status": f"skipped: {runner.stopped}"}
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    fixture = ev.get("fixture")
    work, _ = prepare_work((ev_root / fixture) if fixture else None, ev.get("setup"))
    try:
        overlay = setup_arm(kind, name, source, args, work, run_dir, base, args.shadow if arm == "without" else ())
        problem = preflight(kind, name, arm, work, overlay, run_dir / "arm/skills")
        if problem:
            runner.stop(f"isolation failed ({arm}): {problem}")
            return {**meta, "status": f"error: {problem}"}
        if args.dry_run:
            print(f"{ev['id']} {arm}: isolation ok")
            return {**meta, "status": "dry run"}
        base_commit = commit_all(work, "arm")
        prompt = ev["prompt"]
        if arm == "without" and kind == "command":
            prompt = ev["baseline_prompt"]
        start = time.time()
        proc = runner.omp(prompt, work, overlay, run_dir / "session", ev.get("max_time", args.max_time))
        stdout, stderr = proc.communicate()
        (run_dir / "events.jsonl").write_text(stdout)
        (run_dir / "stderr.txt").write_text(stderr[-20000:])
        metrics = session_metrics(run_dir / "session", prompt)
        (run_dir / "final.md").write_text(metrics.pop("final"))
        diff = changes(work, base_commit)
        (run_dir / "diff.patch").write_text(diff[:400_000])
        checks = []
        for check in ev.get("checks", []):
            res = subprocess.run(check["run"], shell=True, cwd=work, capture_output=True, text=True, check=False,
                                 timeout=check.get("timeout", 600))
            checks.append({"name": check["name"], "passed": res.returncode == 0, "exit_code": res.returncode,
                           "output": (res.stdout + res.stderr)[-3000:]})
        (run_dir / "checks.json").write_text(json.dumps(checks, indent=2))
        metrics = {**meta, "prompt": prompt, "exit_code": proc.returncode, "seconds": round(time.time() - start, 1), **metrics}
        (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
        runner.charge(metrics["cost"])
        passed = sum(c["passed"] for c in checks)
        print(f"{ev['id']} {arm} #{rep}: exit {proc.returncode}, ${metrics['cost']:.2f}, {metrics['seconds']}s, "
              f"checks {passed}/{len(checks)}, total ${runner.spent:.2f}", flush=True)
        return {**meta, "status": "done", "dir": str(run_dir.relative_to(runner.out))}
    finally:
        if not args.keep:
            shutil.rmtree(work.parent, ignore_errors=True)


def load_evals(path: Path) -> dict:
    data = json.loads(path.read_text())
    ids = [e["id"] for e in data.get("evals", [])]
    if len(ids) != len(set(ids)):
        sys.exit("eval ids must be unique")
    for ev in data.get("evals", []):
        ev.setdefault("fixture", data.get("fixture"))
        ev.setdefault("setup", data.get("setup"))
    return data


def resolve_paths(args: argparse.Namespace) -> None:
    """Absolute paths: trials run from other directories and overlays name these paths."""
    for key in ("target", "evals", "out"):
        setattr(args, key, getattr(args, key).resolve())


def cmd_run(args: argparse.Namespace) -> None:
    resolve_paths(args)
    kind, name = target_kind(args.target)
    data = load_evals(args.evals)
    evals = [e for e in data["evals"] if not args.eval or e["id"] in args.eval][: args.limit or None]
    arms = args.arm or ["without", "with"]
    if kind == "command" and "without" in arms and any(not e.get("baseline_prompt") for e in evals):
        sys.exit("a command's without arm needs a baseline_prompt in every eval")
    args.out.mkdir(parents=True, exist_ok=True)
    sources = {arm: arm_source(arm, args.target, args.out / "arms") for arm in arms}
    runner = Runner(args, args.out)
    base = effective_base()
    ref_paths = references(name, args.target, AGENT_DIR)
    args.shadow = [p.stem for p in ref_paths if p.parent.name == "rules"] if args.shadow_references else []
    refs = [str(p) for p in ref_paths if p.stem not in args.shadow or p.parent.name != "rules"]
    for ref in refs:
        print(f"note: {ref} points at {name} and stays installed in every arm, without included")
    for rule in args.shadow:
        print(f"note: the without arm hides the user rule {rule}, which points at {name}")
    jobs = [(e, arm, rep) for e in evals for rep in range(1, args.reps + 1) for arm in arms]
    print(f"{kind} {name}: {len(evals)} evals x {len(arms)} arms x {args.reps} reps = {len(jobs)} runs, budget ${args.budget}")
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda j: run_one(runner, kind, name, j[0], args.evals.parent, j[1], sources[j[1]], j[2], base), jobs))
    index = {"target": str(args.target), "kind": kind, "name": name, "arms": arms, "model": args.model, "references": refs,
             "shadowed_in_without": args.shadow,
             "evals": {e["id"]: {k: e.get(k) for k in ("prompt", "baseline_prompt", "expectations")} for e in evals},
             "runs": results, "spent": round(runner.spent, 4), "stopped": runner.stopped}
    (args.out / "index.json").write_text(json.dumps(index, indent=2))
    for arm in arms:
        checks = [c["passed"] for r in results if r["arm"] == arm and r["status"] == "done"
                  for c in json.loads((args.out / r["dir"] / "checks.json").read_text())]
        if checks:
            print(f"METRIC checks_{re.sub(r'[^\w]', '_', arm)}={sum(checks) / len(checks):.4f}")
    print(f"spent ${runner.spent:.2f}" + (f"; stopped: {runner.stopped}" if runner.stopped else ""))
    if runner.stopped:
        sys.exit(1)


def cmd_triggers(args: argparse.Namespace) -> None:
    resolve_paths(args)
    kind, name = target_kind(args.target)
    if kind == "command":
        sys.exit("commands are started by the user; they have no trigger to test")
    data = load_evals(args.evals)
    queries = [q for q in data.get("triggers", []) if args.split == "all" or q.get("split", "train") == args.split]
    if not queries:
        sys.exit(f"no trigger queries for split {args.split}")
    if kind == "skill":
        hint, origin = skill_hint(args.target if args.target.name == "SKILL.md" else args.target / "SKILL.md")
        print(f"hint: {hint}  [{origin}]")
    args.out.mkdir(parents=True, exist_ok=True)
    source = arm_source(args.arm, args.target, args.out / "arms")
    runner = Runner(args, args.out)
    base = effective_base()
    loads = (f"skill://{name}", f"rule://{name}")

    def probe(job: tuple[int, dict, int]) -> dict:
        i, q, rep = job
        if not runner.admit():
            return {"query": i, "rep": rep, "status": f"skipped: {runner.stopped}"}
        run_dir = args.out / "triggers" / f"q{i}-{rep}"
        shutil.rmtree(run_dir, ignore_errors=True)
        run_dir.mkdir(parents=True)
        work, _ = prepare_work((args.evals.parent / q["fixture"]) if q.get("fixture") else None, None)
        try:
            overlay = setup_arm(kind, name, source, args, work, run_dir, base)
            problem = preflight(kind, name, args.arm, work, overlay, run_dir / "arm/skills")
            if problem:
                runner.stop(f"isolation failed: {problem}")
                return {"query": i, "rep": rep, "status": f"error: {problem}"}
            proc = runner.omp(q["query"], work, overlay, run_dir / "session", args.max_time)
            triggered, calls = False, 0
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
                    path = str((c.get("arguments") or {}).get("path", ""))
                    triggered = triggered or path.startswith(loads) or path.endswith(f"/{name}/SKILL.md")
                if triggered or calls >= args.max_tool_calls:
                    break
            proc.kill()
            proc.wait()
            cost = session_metrics(run_dir / "session", q["query"])["cost"]
            runner.charge(cost)
            return {"query": i, "rep": rep, "status": "done", "triggered": triggered, "cost": cost}
        finally:
            shutil.rmtree(work.parent, ignore_errors=True)

    jobs = [(i, q, rep) for i, q in enumerate(queries) for rep in range(1, args.reps + 1)]
    print(f"{len(queries)} queries x {args.reps} reps = {len(jobs)} runs ({args.split}), budget ${args.budget}")
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(probe, jobs))
    rows, correct = [], 0
    for i, q in enumerate(queries):
        done = [r for r in results if r["query"] == i and r["status"] == "done"]
        rate = sum(r["triggered"] for r in done) / len(done) if done else None
        ok = rate is not None and (rate >= 0.5) == bool(q["should_trigger"])
        correct += ok
        rows.append({**q, "rate": rate, "runs": len(done), "correct": ok})
        print(f"{'ok  ' if ok else 'MISS'} {rate if rate is not None else '-'} should={q['should_trigger']}: {q['query'][:90]}")
    accuracy = correct / len(queries)
    (args.out / f"triggers-{args.split}.json").write_text(json.dumps({"target": name, "split": args.split, "accuracy": accuracy,
                                                                      "queries": rows, "spent": runner.spent}, indent=2))
    print(f"METRIC trigger_accuracy_{args.split}={accuracy:.4f}")
    print(f"spent ${runner.spent:.2f}" + (f"; stopped: {runner.stopped}" if runner.stopped else ""))


def cmd_rules(args: argparse.Namespace) -> None:
    kind, _ = target_kind(args.target)
    if kind != "rule":
        sys.exit("rules needs a rules/*.md target")
    cases = load_evals(args.evals).get("rule_cases", [])
    if not cases:
        sys.exit("the eval set has no rule_cases")
    failed = 0
    for case in cases:
        cmd = ["omp", "ttsr", "test", "--rule", str(args.target.resolve()), "--source", case.get("source", "tool"), "--json", "--file", "-"]
        if case.get("source", "tool") == "tool":
            cmd += ["--tool", case.get("tool", "edit")]
        if case.get("path"):
            cmd += ["--path", case["path"]]
        if case.get("agent"):
            cmd += ["--agent", case["agent"]]
        out = subprocess.run(cmd, input=case["snippet"], capture_output=True, text=True, check=True, cwd=tempfile.gettempdir())
        verdict = ttsr_verdict(json.loads(out.stdout))
        want = "fires" if case["fires"] else "quiet"
        status = "untested (question rule: the CLI does not judge)" if verdict == "question" else "ok" if verdict == want else "FAIL"
        failed += status == "FAIL"
        print(f"{status}: expected {want}, got {verdict}: {case.get('path', '')} {case['snippet'][:60]!r}")
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
        p.add_argument("--budget", type=float, required=True, help="stop starting runs once this many USD are spent")
        p.add_argument("--max-cost", type=float, default=3.0, help="USD cap per run (omp --max-cost)")
        p.add_argument("--max-time", default="20m")
        p.add_argument("--model")
        p.add_argument("--thinking")
        p.add_argument("--jobs", type=int, default=4)
        p.add_argument("--advisor", action="store_true", help="keep the advisor on, as in the user's sessions")
        p.add_argument("--keep", action="store_true", help="keep the trial working copies under /tmp")
    run = sub.choices["run"]
    run.add_argument("--arm", action="append", help="with, without, old=<git-rev>; repeatable (default: without, with)")
    run.add_argument("--reps", type=int, default=3)
    run.add_argument("--eval", action="append", help="run only this eval id; repeatable")
    run.add_argument("--limit", type=int, help="run only the first N evals")
    run.add_argument("--dry-run", action="store_true", help="install each arm and check its isolation; no model calls")
    run.add_argument("--shadow-references", action="store_true",
                     help="in the without arm, also hide user rules that point at the target (skill:// or rule://)")
    trig = sub.choices["triggers"]
    trig.add_argument("--arm", default="with")
    trig.add_argument("--reps", type=int, default=3)
    trig.add_argument("--split", choices=["train", "test", "all"], default="train")
    trig.add_argument("--max-tool-calls", type=int, default=4, help="not triggered after this many other tool calls")
    trig.set_defaults(max_time="5m")
    rules = sub.add_parser("rules", parents=[common], help="offline rule trigger cases")
    rules.add_argument("--evals", type=Path, required=True)
    sub.add_parser("hint", parents=[common], help="the routing hint the model sees for a skill")
    args = parser.parse_args()
    {"run": cmd_run, "triggers": cmd_triggers, "rules": cmd_rules, "hint": cmd_hint}[args.cmd](args)


if __name__ == "__main__":
    main()
