#!/usr/bin/env python3
"""Digest the omp sessions of a project for guidance error analysis.

Writes one Markdown digest per main session and prints an index. The digest
format is in ../session-analysis.md.

Without arguments the project is the current directory and the window starts
where its last review ended: the newest `guidance-review-window <since>
<until> <project>` line naming this project in an assistant reply of its
sessions, else 14 days ago. A run with --project needs --since and prints no
such line, so a review of other projects never moves this one's window. The
running session is left out.
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from itertools import islice
from pathlib import Path

SESSIONS = Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".omp/agent") / "sessions"
MARKER = "guidance-review-window"
REVIEW = re.compile(MARKER + r" \d{4}-\d\d-\d\dT\d\d:\d\dZ (\d{4}-\d\d-\d\dT\d\d:\d\d)Z ([^`\n]+)")
WRAPPER = re.compile(r"<(system-reminder|system-notice|EXTREMELY_IMPORTANT|file|memories|irc)\b.*?</\1>", re.S)
ADVISORY = re.compile(r"<advisory\b[^>]*severity=\"(\w+)\"[^>]*>(.*?)</advisory>", re.S)
INTERRUPT = re.compile(r"<system-(interrupt|reminder) [^>]*rule=\"([^\"]+)\"")
MATCHED = re.compile(r"Matched: \"(.*?)\"\n")
LOAD = re.compile(r"(skill|rule)://[^?#:\s]+")
EDIT_HEAD = re.compile(r"^\[([^\]#]+)#", re.M)
GUIDANCE = re.compile(
    r"(^|/)(AGENTS|CLAUDE|RULES|WATCHDOG|SKILL)\.(md|ya?ml)$"
    r"|(^|/)\.?omp/(agent/)?(rules|skills|commands|agents|extensions)/"
    r"|(^|/)skills/[^/]+/"
)
SHELL_EDIT = re.compile(r"\b(?:rm|mv)\s[^;&|\n]*(?:\.omp/|AGENTS\.md|SKILL\.md)[^;&|\n]*")
SUBAGENT_KINDS = {"RULE", "LOAD", "EDIT", "ABORT", "ERROR"}


def minute(value: str) -> str:
    """`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM[Z]` as `YYYY-MM-DDTHH:MM`, which sorts against entry timestamps."""
    value = value.rstrip("Z")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M" if "T" in value else "%Y-%m-%d").strftime("%Y-%m-%dT%H:%M")


def entries(path: Path):
    """(line number, entry); a half-written last line of a live session is skipped."""
    with path.open() as lines:
        for number, line in enumerate(lines, 1):
            try:
                yield number, json.loads(line)
            except json.JSONDecodeError:
                continue


def blocks_of(message: dict) -> list[dict]:
    content = message.get("content") or []
    return [{"type": "text", "text": content}] if isinstance(content, str) else content


def text_of(message: dict) -> str:
    return " ".join(block["text"] for block in blocks_of(message) if block.get("type") == "text")


def project_roots(project: Path) -> list[Path]:
    """The project directory and the git worktrees of its repository."""
    listing = subprocess.run(
        ["git", "-C", project, "worktree", "list", "--porcelain"], capture_output=True, text=True
    ).stdout
    worktrees = [Path(line[9:]) for line in listing.splitlines() if line.startswith("worktree ")]
    return [path.resolve() for path in [project, *worktrees]]


def main_sessions(roots: list[Path], since: str) -> list[Path]:
    """Main sessions started in a root (or below it) and written at or after `since`."""
    running = os.environ.get("PI_SESSION_FILE", "")
    found = []
    for path in SESSIONS.glob("*/*.jsonl"):
        if running.startswith(str(path.with_suffix(""))):
            continue
        if datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M") < since:
            continue
        head = (entry for _, entry in islice(entries(path), 5))  # the header follows the title slot
        header = next((entry for entry in head if entry.get("type") == "session"), {})
        cwd = Path(header.get("cwd", ""))
        if any(cwd == root or root in cwd.parents for root in roots):
            found.append(path)
    return sorted(found, key=lambda path: path.name)


def last_review(paths: list[Path], project: Path) -> tuple[str, Path] | None:
    """End of the newest finished review of `project` and the session that reported it."""
    newest = None
    for path in paths:
        with path.open() as lines:
            for line in lines:
                if MARKER not in line:
                    continue  # cheap filter: most lines are never parsed
                try:
                    message = json.loads(line).get("message") or {}
                except json.JSONDecodeError:
                    continue
                if message.get("role") != "assistant":
                    continue
                for until, reviewed in REVIEW.findall(text_of(message)):
                    if reviewed.strip() == str(project) and (newest is None or until > newest[0]):
                        newest = (until, path)
    return newest


def squeeze(text: str, limit: int) -> str:
    text = " ".join(WRAPPER.sub(" ", text).split())
    return text if len(text) <= limit else f"{text[:limit]} …"


def digest(path: Path, since: str, until: str, main: bool) -> tuple[list[str], dict[str, int]]:
    """Digest lines for entries in [since, until) and a count of each kind."""
    lines: list[str] = []
    counts: dict[str, int] = {}
    calls: dict[str, int] = {}  # tool call id -> index of its digest line
    parents: dict[str, str] = {}  # entry id -> parent id, to find the reply a user turn answers
    replies: dict[str, tuple[int, str, str]] = {}  # entry id -> (line, timestamp, assistant text)
    interrupted: list[str] = []
    day = ""

    def add(stamp: str, number: int, kind: str, text: str) -> None:
        nonlocal day
        if not main and kind not in SUBAGENT_KINDS:
            return
        if stamp[:10] != day:
            day = stamp[:10]
            lines.append(f"\n## {day}" if main else f"({day})")
        lines.append(f"{stamp[11:19]} L{number} {kind:<7} {text}".rstrip())
        counts[kind] = counts.get(kind, 0) + 1

    for number, entry in entries(path):
        stamp = entry.get("timestamp")
        if not isinstance(stamp, str):
            continue
        kind = entry.get("type")
        message = entry.get("message") or {}
        role = message.get("role")
        if "id" in entry:
            parents[entry["id"]] = entry.get("parentId")
            text = text_of(message)
            if kind == "message" and role == "assistant" and text.strip():
                replies[entry["id"]] = (number, stamp, text)
        if not since <= stamp < until:
            continue
        if kind == "ttsr_injection":
            names = entry.get("injectedRules") or []
            if names != interrupted:
                add(stamp, number, "RULE", ", ".join(names))
            interrupted = []
        elif kind == "custom_message":
            content = str(entry.get("content"))
            if entry.get("customType") == "ttsr-injection":
                found = INTERRUPT.findall(content)
                interrupted = [name for _, name in found]
                verb = "interrupted" if any(tag == "interrupt" for tag, _ in found) else "reminded after the call"
                matched = MATCHED.search(content)
                hit = squeeze(matched[1], 160) if matched else "?"
                add(stamp, number, "RULE", f"{', '.join(interrupted)} {verb}: {hit}")
            elif entry.get("customType") == "advisor":
                for severity, note in ADVISORY.findall(content):
                    add(stamp, number, "ADVISOR", f"{severity}: {squeeze(note, 300)}")
            elif entry.get("customType") == "session-stop-continuation":
                add(stamp, number, "GATE", squeeze(content, 200))
        if kind != "message":
            continue
        if role == "toolResult":
            if message.get("isError") and message.get("toolCallId") in calls:
                lines[calls[message["toolCallId"]]] += " (failed)"
        elif role == "assistant":
            error = message.get("errorMessage") or ""
            if message.get("stopReason") == "aborted" and error == "Interrupted by user":
                add(stamp, number, "ABORT", "")
            elif message.get("stopReason") == "error":
                add(stamp, number, "ERROR", squeeze(error, 120))
            for block in blocks_of(message):
                if block.get("type") != "toolCall":
                    continue
                arguments = block.get("arguments") or {}
                target = str(arguments.get("path", ""))
                before = len(lines)
                if block["name"] == "read" and (load := LOAD.match(target)):
                    add(stamp, number, "LOAD", load[0])
                elif block["name"] in ("edit", "write"):
                    touched = EDIT_HEAD.findall(str(arguments.get("input", ""))) or [target]
                    guidance = sorted({name for name in touched if GUIDANCE.search(name)})
                    if guidance:
                        add(stamp, number, "EDIT", ", ".join(guidance))
                elif block["name"] == "bash":
                    for command in SHELL_EDIT.findall(str(arguments.get("command", ""))):
                        add(stamp, number, "EDIT", squeeze(command, 160))
                if len(lines) > before:
                    calls[block.get("id")] = len(lines) - 1
        elif role == "user" and message.get("attribution") in (None, "user"):
            text = squeeze(text_of(message), 600)
            if not text:
                continue
            ancestor = entry.get("parentId")
            while ancestor and ancestor not in replies:
                ancestor = parents.get(ancestor)
            if ancestor:
                reply_line, reply_stamp, reply = replies[ancestor]
                add(reply_stamp, reply_line, "AGENT", squeeze(reply, 300))
            add(stamp, number, "USER", ("(mid-run) " if message.get("steering") else "") + text)
    return lines, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, action="append", help="project directory, repeatable; needs --since")
    parser.add_argument("--since", type=minute, help="window start, UTC: YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    parser.add_argument("--until", type=minute, help="window end, exclusive (default: now)")
    parser.add_argument("--match", type=re.compile, help="keep only sessions whose digest matches this regex")
    parser.add_argument("--out", type=Path, help="new or empty directory for the digests (default: a fresh temp dir)")
    args = parser.parse_args()

    if args.project and not args.since:
        parser.error("--project needs --since: the last review is looked up only for the current directory")
    projects = [path.resolve() for path in args.project or [Path.cwd()]]
    for project in projects:
        if not project.is_dir():
            parser.error(f"not a directory: {project}")
    if args.out and args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        parser.error(f"--out must be a new or empty directory: {args.out}")
    now = datetime.now(UTC)
    until = args.until or now.strftime("%Y-%m-%dT%H:%M")
    since, origin = args.since, "--since"
    if since is None:
        lookback = (now - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M")
        review = last_review(main_sessions(project_roots(projects[0]), lookback), projects[0])
        if review:
            since, origin = review[0], f"end of the last review, reported in {review[1].name}"
        else:
            since = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M")
            origin = "no earlier review found: last 14 days"
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    out = args.out or Path(tempfile.mkdtemp(prefix=f"guidance-sessions-{projects[0].name}-"))

    print(f"projects: {', '.join(map(str, projects))}")
    print(f"window:   [{since}, {until}) UTC ({origin})")
    print(f"digests:  {out}\n")
    print("digest | lines | user turns | aborts | rule injections | advisor notes | subagents | transcript")
    roots = [root for project in projects for root in project_roots(project)]
    sessions = turns = 0
    for path in main_sessions(roots, since):
        lines, counts = digest(path, since, until, main=True)
        if not counts.get("USER"):
            continue
        stem = path.stem
        subagents = sorted(
            found
            for found in (path.parent / stem).rglob("*.jsonl")
            if not found.name.startswith("__") and found.name != "changes.jsonl"  # advisors, tool log
        )
        for subagent in subagents:
            sublines, _ = digest(subagent, since, until, main=False)
            if sublines:
                lines += [f"\n### {subagent.stem}", *sublines]
        body = f"# {path}\n" + "\n".join(lines) + "\n"
        if args.match and not args.match.search(body):
            continue
        name = f"{stem[:16]}_{stem[-8:]}.md"
        (out / name).write_text(body)
        sessions, turns = sessions + 1, turns + counts["USER"]
        print(
            f"{name} | {len(lines)} | {counts['USER']} | {counts.get('ABORT', 0)} | {counts.get('RULE', 0)}"
            f" | {counts.get('ADVISOR', 0)} | {len(subagents)} | {path}"
        )
    print(f"\n{sessions} sessions, {turns} user turns")
    if not args.project:
        print(f"report line: {MARKER} {since}Z {until}Z {projects[0]}")


if __name__ == "__main__":
    main()
