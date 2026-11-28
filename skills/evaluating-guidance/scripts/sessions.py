#!/usr/bin/env python3
"""Digest omp sessions, record review progress, or extract rule test cases."""

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from itertools import islice
from pathlib import Path

URL_PATH = re.compile(r"^[a-z][a-z0-9+.-]*://")  # internal URLs (local://, xd://) are no project files


WRAPPER = re.compile(r"<(system-reminder|system-notice|EXTREMELY_IMPORTANT|file|memories|irc)\b.*?</\1>", re.S)
ADVISORY = re.compile(r'<advisory\b[^>]*severity="(\w+)"[^>]*>(.*?)</advisory>', re.S)
RULE_BLOCK = re.compile(r'(?:<|&lt;)system-(interrupt|reminder)\b([^>]*)>(.*?)(?:<|&lt;)/system-\1>', re.S)
ATTRIBUTE = re.compile(r'([\w-]+)="([^"]*)"')
MATCHED = re.compile(r'^Matched: "(.*)"$', re.M)
LOAD_TARGET = re.compile(r"((?:skill|rule)://[^?#:\s;]+)")
SKILL_INVOKED = re.compile(r'^\[IMPORTANT: User invoked the "([^"]+)" skill\b')
SKILL_PATH = re.compile(r"^---\n\nSkill: (.+[/\\]SKILL\.md)$", re.M)
HASHLINE = re.compile(r"^\[([^\]#]+)#[0-9A-Za-z]{4}\]\s*$")
APPLY_PATCH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$")
TASK_RESULT = re.compile(r"<task-result\b([^>]*)>(.*?)</task-result>", re.S)
TASK_OUTPUT = re.compile(r"<(output|error)>\s*(.*?)\s*</\1>", re.S)
FINAL_STATUS = {"completed", "failed", "aborted"}
GUIDANCE = re.compile(
    r"(^|/)(AGENTS|CLAUDE|RULES|WATCHDOG|SKILL)\.(md|ya?ml)$"
    r"|(^|/)\.?omp/(agent/)?(rules|skills|commands|agents|extensions)/"
    r"|(^|/)skills/[^/]+/"
)
SHELL_EDIT = re.compile(r"\b(?:rm|mv)\s[^;&|\n]*(?:\.omp/|AGENTS\.md|SKILL\.md)[^;&|\n]*")


def timestamp(value: str) -> str:
    """UTC window bounds share the ISO spelling of persisted stamps, without Z."""
    try:
        date = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid UTC time: {value}") from exc
    if date.tzinfo is not None:
        date = date.astimezone(UTC).replace(tzinfo=None)
    return date.isoformat(timespec="microseconds")


def stamp_key(stamp):
    whole, _, fraction = stamp.rstrip("Z").partition(".")
    return f"{whole}.{fraction.ljust(6, '0')}"


def in_window(stamp, since, until):
    return since <= stamp_key(stamp) < until


def session_root(explicit):
    return Path(explicit or os.environ.get("GUIDANCE_SESSIONS") or
                Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".omp/agent") / "sessions").expanduser().resolve()


def entries(path):
    """Read physical JSONL lines; a live session may have an incomplete tail."""
    with path.open(encoding="utf-8", errors="replace") as lines:
        for number, line in enumerate(lines, 1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                yield number, item


def header(path):
    with contextlib.closing(entries(path)) as rows:
        return next((entry for _, entry in islice(rows, 5) if entry.get("type") == "session"), {})


def project_roots(project):
    listing = subprocess.run(
        ["git", "-C", project, "worktree", "list", "--porcelain", "-z"], capture_output=True, text=True
    ).stdout
    return {project, *(Path(item[9:]).resolve() for item in listing.split("\0") if item.startswith("worktree "))}


def bucket_prefixes(path):
    def encode(parts):
        return re.sub(r"[/\\:]", "-", "/".join(parts))

    yield f"--{encode(path.parts[1:])}", "--"
    for base, prefix in ((Path.home().resolve(), "-"), (Path(tempfile.gettempdir()).resolve(), "-tmp"),
                         (Path("/tmp"), "-tmp")):
        if path.is_relative_to(base):
            relative = encode(path.relative_to(base).parts)
            yield prefix.rstrip("-") + "-" + relative if relative else prefix, ""


def selected_path(path, root, excludes, running):
    return not any(
        fnmatchcase(str(value), pattern)
        for value in (path, path.relative_to(root), path.name)
        for pattern in excludes
    ) and (running is None or path.resolve().with_suffix("") != running.with_suffix(""))


def candidates(root, roots, excludes, since, until, *, live):
    """Narrow by bucket, filename and append mtime before reading headers."""
    prefixes = {pair for project in roots for pair in bucket_prefixes(project)}
    running = os.environ.get("PI_SESSION_FILE")
    running = Path(running).expanduser().resolve() if running else None
    cutoff = datetime.fromisoformat(since).replace(tzinfo=UTC).timestamp()
    if not root.is_dir():
        return
    buckets = [
        bucket for bucket in root.iterdir()
        if bucket.is_dir() and any(
            bucket.name == prefix + suffix or
            (bucket.name.startswith(prefix if prefix in {"-", "--"} else prefix + "-") and bucket.name.endswith(suffix))
            for prefix, suffix in prefixes
        )
    ]
    for path in sorted((p for b in buckets for p in b.glob("*.jsonl")), key=lambda p: (p.name, p.parent)):
        if not selected_path(path, root, excludes, running):
            continue
        children = sorted(
            child for child in path.with_suffix("").rglob("*.jsonl")
            if not child.name.startswith("__") and child.name != "changes.jsonl"
            and selected_path(child, root, excludes, running)
            and (not live or child.stat().st_mtime >= cutoff)
        )
        main_recent = not live or path.stat().st_mtime >= cutoff
        if not (main_recent or children):
            continue
        head = header(path)
        cwd = head.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            continue
        canonical = Path(cwd).resolve()
        if not any(canonical.is_relative_to(project) for project in roots):
            continue
        # The header is written when the session starts. Newer live sessions
        # cannot have events in the requested window.
        if live and isinstance(head.get("timestamp"), str) and stamp_key(head["timestamp"]) >= until:
            continue
        yield path, main_recent, children


def blocks(message):
    content = message.get("content") or []
    return [{"type": "text", "text": content}] if isinstance(content, str) else content


def text_of(message):
    return "\n".join(block["text"] for block in blocks(message) if block.get("type") == "text")


def unique(values):
    return list(dict.fromkeys(values))


def tool_files(tool, arguments):
    """Project edit/write arguments to the matcher-visible text for each file."""
    path = arguments.get("path") or arguments.get("file_path")
    if tool == "write":
        if path:
            yield path, arguments.get("content", "")
        return
    payload = arguments.get("input", "")
    if not isinstance(payload, str):
        return
    by_path = {}
    active = None
    for line in payload.split("\n"):
        section = HASHLINE.fullmatch(line) or APPLY_PATCH.fullmatch(line)
        if section:
            active = by_path.setdefault(section[1], [])
        elif active is not None and line.startswith("+"):
            active.append(line[1:])
    if by_path:
        for path, lines in by_path.items():
            yield path, "\n".join(lines)
    elif path:
        yield path, arguments.get("new_string", arguments.get("newString", ""))


def custom_rule(entry):
    content = text_of(entry)
    details = entry.get("details") or {}
    tags = list(rule_blocks(content))
    mode = "unknown"
    if tags and all(tag == "interrupt" for tag, _, _ in tags):
        mode = "interrupt"
    elif tags and all(body.lstrip().startswith("Rule judge flagged") for _, _, body in tags):
        mode = "judged"
    matched = {rule: hit[1] for _, rule, body in tags if (hit := MATCHED.search(body))}
    matched.update(details.get("matched") or {})
    return unique(details.get("rules") or [rule for _, rule, _ in tags]), mode, matched


def rule_blocks(content):
    for kind, attrs, body in RULE_BLOCK.findall(content):
        rule = dict(ATTRIBUTE.findall(attrs)).get("rule")
        if rule:
            yield kind, rule, body


def read_targets(arguments):
    return unique(m[1] for target in str(arguments.get("path", "")).split(";")
                  if (m := LOAD_TARGET.match(target.lstrip())))


def is_body(target):
    return "/" not in target.split("://", 1)[1] or target.endswith("/SKILL.md")


def selected_skill(entry, message):
    """Use invocation metadata or the wrapper emitted by the skill loader."""
    source = entry if entry.get("type") == "custom_message" else message
    if source.get("customType") == "skill-prompt":
        name = (source.get("details") or {}).get("name")
        if isinstance(name, str) and name:
            return f"skill://{name}", "invoked" if source.get("attribution") == "user" else "autoload"
    if (source.get("customType") in {"skill-prompt", "custom-message"} or
            message.get("synthetic") or message.get("role") == "developer"):
        value = text_of(source)
        if hit := SKILL_INVOKED.match(value):
            return f"skill://{hit[1]}", "invoked"
        if hit := SKILL_PATH.search(value):
            return f"skill://{Path(hit[1]).parent.name}", "autoload"
    return None


def task_results(source):
    """Read final statuses from task results, not task-start progress snapshots."""
    details = source.get("details") or {}
    content = text_of(source)
    tagged = {}
    for attrs, body in TASK_RESULT.findall(content):
        fields = dict(ATTRIBUTE.findall(attrs))
        if child := fields.get("id"):
            output = TASK_OUTPUT.search(body)
            tagged[child] = (fields.get("status"), output[2] if output else body.strip())
    jobs = [job for job in details.get("jobs") or [] if job.get("type") == "task"]
    results = jobs or details.get("results") or ({"id": child} for child in tagged)
    for result in results:
        child = result.get("agentId") or result.get("id") or result.get("jobId") or result.get("agent")
        if not child:
            continue
        status, value = tagged.get(child, (None, ""))
        status = (result.get("status") or status or "").lower()
        if not status and isinstance(result.get("exitCode"), int):
            status = "aborted" if result.get("aborted") else "failed" if result["exitCode"] else "completed"
        if status in FINAL_STATUS:
            value = value or result.get("resultText") or result.get("errorText") or result.get("output") or result.get("result") or result.get("error") or ""
            yield {"agent": child, "status": status, "result": str(value)[:200]}, result.get("settledAtMs")


def correlate_reminder(entry, message, parents, injections, batch, tool_results, delivered):
    names = {name: body for kind, name, body in rule_blocks(text_of(message)) if kind == "reminder"}
    if not names or batch is None:
        return
    ancestor = entry.get("parentId")
    claims = defaultdict(list)
    saw_result = False
    while ancestor is not None and ancestor != batch:
        if ancestor in tool_results:
            saw_result = True
        if (row := injections.get(ancestor)) is not None and row["data"]["mode"] == "unknown":
            for name in row["data"]["rules"]:
                claims[name].append(row)
        ancestor = parents.get(ancestor)
    if not saw_result or ancestor != batch:
        return
    for name in names:
        if len(claims[name]) != 1:
            continue
        data = claims[name][0]["data"]
        rules = data["rules"]
        if data["mode"] == "unknown" and all(rule in names and claims[rule] == claims[name] for rule in rules):
            data["mode"] = "tool-reminder"
            data["matched"].update({rule: hit[1] for rule in rules if (hit := MATCHED.search(names[rule]))})
            delivered[batch].extend(rules)


def tool_observations(tool, arguments):
    """Return digest observations and the matcher input, if any, for one call."""
    if tool == "read" and (targets := read_targets(arguments)):
        sub = "body" if all(is_body(target) for target in targets) else "file"
        return [("LOAD", ", ".join(targets), {"targets": targets, "sub": sub, "outcome": "no-result"})], []
    if tool in {"edit", "write"}:
        files = [(path, text) for path, text in tool_files(tool, arguments) if not URL_PATH.match(path)]
        guidance = sorted({path for path, _ in files if GUIDANCE.search(path)})
        if guidance:
            return [("EDIT", ", ".join(guidance), {"tool": tool, "paths": guidance})], files
        return [], files
    if tool == "bash":
        return [("EDIT", cmd, {"tool": tool}) for cmd in SHELL_EDIT.findall(arguments.get("command", ""))], []
    return [], []


def check_result(message):
    tool = message.get("toolName")
    code = (message.get("details") or {}).get("exitCode", message.get("exitCode"))
    data = {"tool": tool, "call": message.get("toolCallId")}
    label = tool or "tool"
    if code is not None:
        data["exit_code"] = code
        label += f" (exit {code})"
    return f"{label}: {text_of(message)}", data


def observe_load(load, result):
    if result.get("isError"):
        load["outcome"] = "failed"
        return
    load["outcome"] = "ok"
    value = text_of(result)
    if re.match(r"^\[?Directory(?: listing)?[: ]", value, re.I):
        load["sub"] = "listing"
    elif value.startswith(("[Skill file:", "[Rule file:")):
        load["sub"] = "body"


def events(path, actor, since, until, *, collect_cases=False):
    rows, edits = [], []
    parents, batch_at, reply_at = {}, {}, {}
    loads, written, tool_results = {}, defaultdict(list), set()
    custom_rules, injections, delivered, pending = {}, {}, defaultdict(list), []
    seen_replies, settled_tasks = set(), set()
    last_reply = None

    for number, entry in entries(path):
        stamp = entry.get("timestamp")
        if not isinstance(stamp, str):
            continue
        inside = in_window(stamp, since, until)
        entry_id, parent = entry.get("id"), entry.get("parentId")
        message = entry.get("message") or {}
        role, kind = message.get("role"), entry.get("type")
        batch, reply = batch_at.get(parent), reply_at.get(parent)
        if entry_id is not None:
            parents[entry_id] = parent
            batch_at[entry_id] = entry_id if role == "assistant" else batch
            reply_at[entry_id] = reply

        def row(kind, text="", data=None):
            event = {"kind": kind, "line": number, "stamp": stamp, "entry": entry_id,
                     "parent": parent, "actor": actor, "text": text, "data": data or {}}
            if actor != "main":
                event["file"] = str(path)
            return event

        def add(kind, value="", data=None):
            if inside:
                rows.append(row(kind, value, data))

        if kind == "ttsr_injection":
            rules = unique(entry.get("injectedRules") or [])
            extra, mode, matched = custom_rules.get(parent, ([], "unknown", {}))
            if rules and extra and set(rules) != set(extra):
                mode, matched = "unknown", {}
            rules = rules or extra
            event = row("RULE", data={"rules": rules, "mode": mode, "matched": dict(matched)})
            injections[entry_id] = event
            if inside:
                rows.append(event)
            if rules and mode != "unknown" and batch is not None:
                delivered[batch].extend(rules)
            elif rules:
                pending.append((batch, event))  # a later developer reminder may still tie it to its batch
        elif kind == "custom_message":
            custom_type = entry.get("customType")
            if custom_type == "ttsr-injection":
                custom_rules[entry_id] = custom_rule(entry)
            elif inside and custom_type == "advisor":
                for severity, note in ADVISORY.findall(text_of(entry)):
                    add("ADVISOR", f"{severity}: {note.strip()}", {"severity": severity})
            elif inside and custom_type == "session-stop-continuation":
                add("GATE", text_of(entry))
            elif inside and custom_type == "async-result":
                for data, _ in task_results(entry):
                    add("TASK", task_line(data), data)
        elif kind == "compaction":
            add("COMPACT", entry.get("summary") or entry.get("shortSummary") or "",
                {key: entry[key] for key in ("method", "tokensBefore", "tokensAfter") if key in entry})
        elif kind == "model_change":
            add("MODEL", entry.get("model") or "", {"role": entry.get("role") or "default"})

        if role == "assistant":
            answer = text_of(message)
            if answer.strip():
                last_reply = row("AGENT", answer)
                reply_at[entry_id] = last_reply
            if not inside:
                continue
            error = message.get("errorMessage") or ""
            if message.get("stopReason") == "aborted" and error == "Interrupted by user":
                add("ABORT")
            elif message.get("stopReason") == "error":
                add("ERROR", error)
            for block in blocks(message):
                if block.get("type") != "toolCall":
                    continue
                tool, call = block.get("name"), block.get("id")
                observations, files = tool_observations(tool, block.get("arguments") or {})
                for observation, value, data in observations:
                    if observation == "LOAD":
                        loads[entry_id, call] = data
                    else:
                        written[entry_id, call].append(data)
                    add(observation, value, data)
                if collect_cases:
                    for file, snippet in files:
                        edits.append((entry_id, {"snippet": snippet, "source": "tool", "tool": tool,
                                                 "path": file, "agent": actor, "transcript": str(path),
                                                 "line": number, "entry": entry_id}))
        elif role == "developer":
            correlate_reminder(entry, message, parents, injections, batch, tool_results, delivered)
        elif role == "toolResult":
            call = message.get("toolCallId")
            if batch is not None:
                tool_results.add(entry_id)
            if (load := loads.get((batch, call))) is not None:
                observe_load(load, message)
            if message.get("isError"):
                for edit in written.get((batch, call), ()):
                    edit["outcome"] = "failed"
                if inside:
                    add("CHECK", *check_result(message))
            tool = message.get("toolName")
            if inside and tool in {"task", "wait"}:
                for data, settled in task_results(message):
                    if tool == "wait" and settled is not None:
                        key = (data["agent"], settled)
                        if key in settled_tasks:
                            continue
                        settled_tasks.add(key)
                    add("TASK", task_line(data), data)
        elif inside and (role == "user" or kind == "custom_message"):
            if (user := user_text(entry, message)).strip():
                if reply is not None and reply["line"] not in seen_replies:
                    rows.append(reply)
                    seen_replies.add(reply["line"])
                add("USER", ("(mid-run) " if message.get("steering") else "") + user)
        if inside and (role in {"user", "developer", "custom"} or kind == "custom_message"):
            if skill := selected_skill(entry, message):
                name, sub = skill
                add("LOAD", name, {"targets": [name], "sub": sub, "outcome": "ok"})

    if last_reply is not None and in_window(last_reply["stamp"], since, until):
        rows.append({**last_reply, "kind": "END"})
    for event in rows:
        if event["kind"] == "RULE":
            data = event["data"]
            names = ", ".join(data["rules"])
            details = "; ".join(map(str, data["matched"].values()))
            event["text"] = f"{names} ({data['mode']})".lstrip() + (f": {details}" if details else "")
    rows.sort(key=lambda row: row["line"])
    unsure = {batch for batch, event in pending if event["data"]["mode"] == "unknown"}
    files = Counter(batch for batch, _ in edits)
    for batch, edit in edits:
        edit["delivered"] = unique(delivered[batch])
        # exact: the batch touched one file and every delivery in it was tied to it; batch: rules of
        # sibling files are included; unknown: a delivery in the batch could not be tied to it.
        edit["delivery"] = "unknown" if batch in unsure else "exact" if files[batch] == 1 else "batch"
    return rows, [edit for _, edit in edits]


def user_text(entry, message):
    if message.get("role") == "user" and message.get("attribution") in {None, "user"}:
        return text_of(message)
    if entry.get("customType") == "skill-prompt" and entry.get("attribution") == "user":
        details = entry.get("details") or {}
        if details.get("prompt"):
            return details["prompt"]
        if name := details.get("name"):
            return f"/skill:{name} {details.get('args', '')}".rstrip()
    return ""


def task_line(data):
    return f"{data['agent']} {data['status']}: {data['result']}"


def squeeze(text, limit):
    text = " ".join(WRAPPER.sub(" ", text).split())
    return text if len(text) <= limit else f"{text[:limit]} …"


def render(path, groups):
    """Markdown lines. Display only: one line per call's reads, model lines only on a change."""
    yield f"# {path}"
    for actor, rows in groups:
        if actor != "main":
            yield ""
            yield f"### {actor}"
        day = model = None
        folded = []
        for index, row in enumerate(rows):
            stamp, kind, data = row["stamp"], row["kind"], row["data"]
            if kind == "MODEL":
                shown = model is not None or actor == "main"
                if row["text"] == model or not shown:
                    model = row["text"]
                    continue
                model = row["text"]
            text = row["text"]
            if kind in {"LOAD", "EDIT"} and data.get("outcome") in {"failed", "no-result"}:
                text += f" ({data['outcome']})"
            following = rows[index + 1] if index + 1 < len(rows) else None
            if kind == "LOAD" and following and following["kind"] == "LOAD" and following["line"] == row["line"]:
                folded.append(text)
                continue
            if folded:
                text, folded = ", ".join([*folded, text]), []
            if stamp[:10] != day:
                day = stamp[:10]
                yield ""
                yield f"## {day}"
            limit = {"USER": 600, "CHECK": 160}.get(kind, 300)
            yield f"{stamp[11:19]} L{row['line']} {kind:<7} {squeeze(text, limit)}".rstrip()


def summarize(name, path, groups, lines, totals, read_totals):
    counts = Counter()
    reads = Counter()
    deliveries = defaultdict(Counter)
    examples = defaultdict(list)
    for _, rows in groups:
        for row in rows:
            kind, data = row["kind"], row["data"]
            counts[kind] += 1
            if kind == "RULE":
                for rule in data["rules"]:
                    deliveries[rule][data["mode"]] += 1
                    if len(examples[rule]) < 3:
                        examples[rule].append(f"{name}:L{row['line']}")
            elif kind == "LOAD" and data["outcome"] == "ok" and data["sub"] in {"body", "file", "listing"}:
                reads.update({f"{scheme}://{target.split('/', 1)[0]}" for uri in data["targets"]
                              for scheme, target in [uri.split("://", 1)]})
    read_totals.update(reads)
    for rule, modes in deliveries.items():
        total = totals.setdefault(rule, {"sessions": 0, "examples": []})
        total["sessions"] += 1
        total["examples"].extend(examples[rule][:3 - len(total["examples"])])
        for mode, count in modes.items():
            total[mode] = total.get(mode, 0) + count
    user_turns = sum(row["kind"] == "USER" for actor, rows in groups if actor == "main" for row in rows)
    subagents = sum(actor != "main" for actor, _ in groups)
    delivered = sum(sum(modes.values()) for modes in deliveries.values())
    print(f"{name} | {lines} | {user_turns} | {counts['ABORT']} | {delivered}"
          f" | {counts['ADVISOR']} | {subagents} | {path}")
    return {"digest": name, "transcript": str(path), "lines": lines, "user_turns": user_turns,
            "subagents": subagents, "deliveries": dict(deliveries), "reads": dict(reads)}


def write_private(path, chunks):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
        handle.writelines(chunks)


def json_text(value):
    return json.dumps(value, ensure_ascii=False) + "\n"


def checkpoint_path(project, root):
    """One checkpoint per project and session history: profiles keep separate histories."""
    default = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "omp-guidance-review"
    directory = Path(os.environ.get("GUIDANCE_REVIEW_STATE") or default).expanduser()
    return directory / (hashlib.sha256(f"{project}\n{root}".encode()).hexdigest() + ".json")


def checkpoint(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def record(directory):
    index = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    if index["match"] is not None or index["excludes"]:
        raise ValueError("cannot record a digest filtered by --match or --exclude")
    if len(index["projects"]) != 1 or index.get("explicit_project"):
        raise ValueError("cannot record a digest made with an explicit --project")
    project = Path(index["projects"][0]).resolve()
    root = session_root(None)
    path = checkpoint_path(project, root)
    previous = checkpoint(path)
    since, until = index["since"], index["until"]
    now = datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")
    if not since < until <= now:
        raise ValueError(f"cannot record the window [{since}, {until}): it must be non-empty and end by now")
    if Path(index["sessions_root"]) != root:
        raise ValueError(f"cannot record a digest of {index['sessions_root']}: it is not this profile's session history")
    if previous and since > previous["until"]:
        raise ValueError(f"cannot record a gap after {previous['until']}")
    if previous and until <= previous["until"]:
        print(f"review is already recorded through {previous['until']} UTC")
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    value = {"project": str(project), "since": since, "until": until, "sessions": len(index["sessions"]),
             "recorded_at": datetime.now(UTC).isoformat()}
    fd, temp = tempfile.mkstemp(prefix=".record-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json_text(value))
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
    print(f"recorded through {until} UTC: {path}")


def analyze(args, root, roots, since, until, *, collect_cases=False):
    sources = candidates(root, roots, getattr(args, "exclude", []), since, until,
                         live=not (args.sessions or os.environ.get("GUIDANCE_SESSIONS")))
    for path, main_recent, children in sources:
        groups, found = [], []
        transcripts = ([(path, "main")] if main_recent else []) + [
            (child, child.stem) for child in children
        ]
        for transcript, actor in transcripts:
            rows, edits = events(transcript, actor, since, until, collect_cases=collect_cases)
            if rows:
                groups.append((actor, rows))
            found.extend(edits)
        yield path, groups, found


def digest(args, root, projects, roots, since, until, origin):
    out = args.out or Path(tempfile.mkdtemp(prefix="guidance-sessions-"))
    if args.out:
        if out.exists() and (not out.is_dir() or any(out.iterdir())):
            raise ValueError(f"--out must be a new or empty directory: {out}")
        out.mkdir(parents=True, exist_ok=True, mode=0o700)
        out.chmod(0o700)
    print(f"projects: {', '.join(map(str, projects))}")
    print(f"window:   [{since}, {until}) UTC ({origin})")
    print(f"digests:  {out.resolve()}\n")
    print("digest | lines | user turns | aborts | rule deliveries | advisor notes | subagents | transcript")
    totals, read_totals, summary = {}, Counter(), []
    names = set()
    for path, groups, _ in analyze(args, root, roots, since, until):
        if not groups or (args.match and not any(args.match.search(row["text"]) for _, rows in groups for row in rows)):
            continue
        stem = f"{path.stem[:16]}_{path.stem[-8:]}"
        if stem in names:
            stem += "_" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
        names.add(stem)
        markdown = list(render(path, groups))
        write_private(out / f"{stem}.md", (line + "\n" for line in markdown))
        write_private(out / f"{stem}.events.jsonl", (json_text(row) for _, rows in groups for row in rows))
        summary.append(summarize(f"{stem}.md", path, groups, len(markdown), totals, read_totals))
    index = {"projects": list(map(str, projects)), "explicit_project": bool(args.project), "since": since,
             "until": until, "match": args.match.pattern if args.match else None, "excludes": args.exclude,
             "sessions_root": str(root), "sessions": summary, "deliveries": totals}
    write_private(out / "index.json", [json_text(index)])
    print(f"\n{len(summary)} sessions, {sum(row['user_turns'] for row in summary)} user turns")
    print("rule | deliveries by mode | deliberate reads | sessions | examples")
    rules = set(totals) | {uri.removeprefix("rule://") for uri in read_totals if uri.startswith("rule://")}
    for rule in sorted(rules):
        data = totals.get(rule, {})
        modes = ", ".join(f"{mode}: {num}" for mode, num in sorted(data.items()) if mode not in {"examples", "sessions"})
        print(f"{rule} | {modes or '-'} | {read_totals[f'rule://{rule}']} | {data.get('sessions', 0)}"
              f" | {', '.join(data.get('examples', []))}")


def in_paths(path, globs, roots):
    """Match globs relative to the first containing project or worktree root."""
    if not globs:
        return True
    candidate = Path(path)
    for root in roots:
        if candidate.is_absolute() and candidate.is_relative_to(root):
            candidate = candidate.relative_to(root)
            break
    return any(candidate.full_match(glob) for glob in globs)


def cases(args, root, roots, since, until):
    delivered = set(args.delivered)
    # A worktree can be nested inside another checkout.
    roots = sorted(roots, key=lambda path: len(path.parts), reverse=True)
    result = [
        edit for _, _, edits in analyze(args, root, roots, since, until, collect_cases=True)
        for edit in edits
        if (not delivered or delivered.intersection(edit["delivered"])) and in_paths(edit["path"], args.path, roots)
    ]
    write_private(args.out, [json_text({"rule_cases": result})])  # holds source text: new file, owner-only


def add_window(parser, *, since_required=False):
    parser.add_argument("--project", type=Path, action="append", help="project directory, repeatable; needs --since")
    parser.add_argument("--since", type=timestamp, required=since_required, help="UTC window start: YYYY-MM-DD or ISO timestamp")
    parser.add_argument("--until", type=timestamp, help="UTC exclusive window end (default: now)")
    parser.add_argument("--sessions", type=Path, help="session root (default: GUIDANCE_SESSIONS or agent sessions)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Without a subcommand, runs digest.")
    commands = parser.add_subparsers(dest="command", metavar="{digest,record,cases}", required=True)
    digest_parser = commands.add_parser("digest", help="write Markdown digests, full events and an index")
    add_window(digest_parser)
    digest_parser.add_argument("--match", help="keep sessions with matching full event text (regex)")
    digest_parser.add_argument("--exclude", action="append", default=[], help="omit transcript path glob, repeatable")
    digest_parser.add_argument("--out", type=Path, help="new/empty directory (default: private temp directory)")
    record_parser = commands.add_parser("record", help="record a completed, unfiltered review window")
    record_parser.add_argument("directory", type=Path, metavar="DIR", help="digest output directory")
    cases_parser = commands.add_parser("cases", help="extract matcher-visible edits and writes as rule cases")
    add_window(cases_parser, since_required=True)
    cases_parser.add_argument("--path", action="append", default=[], metavar="GLOB",
                              help="keep files matching this project- or worktree-relative glob (** allowed), repeatable")
    cases_parser.add_argument("--delivered", action="append", default=[], metavar="RULE",
                              help="keep only edits that delivered this rule live, repeatable")
    cases_parser.add_argument("--out", type=Path, required=True, metavar="FILE", help="rule cases JSON file")
    argv = sys.argv[1:]
    if not argv or argv[0] not in {"digest", "record", "cases", "-h", "--help"}:
        argv = ["digest", *argv]
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            record(args.directory)
            return
        if args.project and not args.since:
            parser.error("--project needs --since")
        projects = [path.expanduser().resolve() for path in args.project or [Path.cwd()]]
        for project in projects:
            if not project.is_dir():
                parser.error(f"not a directory: {project}")
        now = datetime.now(UTC)
        until = args.until or timestamp(now.isoformat())
        root = session_root(args.sessions)
        since, origin = args.since, "--since"
        if since is None:
            previous = checkpoint(checkpoint_path(projects[0], root))
            if previous:
                since, origin = previous["until"], "end of the recorded review"
            else:
                since = timestamp((now - timedelta(days=14)).isoformat())
                origin = "no recorded review: last 14 days"
        if since > until:
            parser.error("--since must not be later than --until")
        roots = {checkout for project in projects for checkout in project_roots(project)}
        if args.command == "cases":
            cases(args, root, roots, since, until)
        else:
            if args.match is not None:
                args.match = re.compile(args.match)
            digest(args, root, projects, roots, since, until, origin)
    except (OSError, ValueError, re.error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
