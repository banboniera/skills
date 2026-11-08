from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, cast

from .arms import USER_ROOT, target_paths
from .contracts import relative_path, validate_target


_SELECTORS = re.compile(r":(?:raw|img|conflicts|\d|-)")


def _without_selector(path: str) -> str:
    match = _SELECTORS.search(path)
    return path[:match.start()] if match else path


def _frozen_path(path: str, cwd: str) -> str | None:
    """Translate sandbox paths, never resolve them against the live host."""
    path = _without_selector(path)
    if path.startswith("/home/eval/"):
        return "HOME/" + path.removeprefix("/home/eval/")
    if path.startswith("~/"):
        return "HOME/" + path[2:]
    if path.startswith(cwd.rstrip("/") + "/"):
        path = path[len(cwd.rstrip("/")) + 1:]
    if path.startswith("/") or "://" in path:
        return None
    normalized = PurePosixPath(path)
    return normalized.as_posix() if ".." not in normalized.parts else None


def _uri_path(path: str, files: set[str]) -> str | None:
    kind, _, name = _without_selector(path).partition("://")
    if kind == "rule":
        relative = f"rules/{name}.md"
    elif kind == "skill":
        skill, slash, subpath = name.partition("/")
        relative = f"skills/{skill}/{subpath if slash else 'SKILL.md'}"
    else:
        return None
    # Native guidance URIs resolve project guidance before user guidance.
    project, user = ".omp/" + relative, USER_ROOT + relative
    return project if project in files else user if user in files else None


def _events(path: Path, files: set[str]) -> tuple[set[str], set[str], bool]:
    reads: set[str] = set()
    fired: set[str] = set()
    pending: dict[str, str] = {}
    unknown = False
    complete = False
    cwd = "/work/repo"
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        decoded: object = json.loads(line)
        if not isinstance(decoded, dict):
            raise ValueError("invalid exposure event")
        event = cast(dict[str, Any], decoded)
        kind = event.get("type")
        if kind == "agent_end":
            complete = True
        elif kind == "session" and isinstance(event.get("cwd"), str):
            cwd = event["cwd"]
        elif kind == "ttsr_triggered":
            rules = event.get("rules")
            if not isinstance(rules, list):
                raise ValueError("invalid rule exposure event")
            for item in cast(list[object], rules):
                if not isinstance(item, dict):
                    raise ValueError("invalid rule exposure event")
                rule = cast(dict[str, Any], item)
                if not isinstance(rule.get("name"), str):
                    raise ValueError("invalid rule exposure event")
                raw_path = rule.get("path")
                resolved = _frozen_path(raw_path, cwd) if isinstance(raw_path, str) else None
                if resolved is None:
                    name = rule["name"]
                    candidates = [p for p in (f".omp/rules/{name}.md", f"{USER_ROOT}rules/{name}.md") if p in files]
                    if len(candidates) > 1:
                        unknown = True
                        continue
                    resolved = candidates[0] if candidates else None
                if resolved is not None and resolved in files:
                    fired.add(resolved)
        elif kind == "tool_execution_start" and event.get("toolName") == "read":
            decoded_args = event.get("args")
            ident = event.get("toolCallId")
            if not isinstance(decoded_args, dict) or not isinstance(ident, str):
                raise ValueError("invalid read exposure event")
            args = cast(dict[str, Any], decoded_args)
            requested = args.get("path")
            if not isinstance(requested, str):
                raise ValueError("invalid read exposure event")
            pending[ident] = requested
        elif kind == "tool_execution_end" and event.get("toolName") == "read":
            ident = event.get("toolCallId")
            if not isinstance(ident, str) or ident not in pending:
                unknown = True
                continue
            requested = pending.pop(ident)
            if event.get("isError") is True:
                continue
            if event.get("isError") is not False:
                unknown = True
                continue
            decoded_result = event.get("result")
            if not isinstance(decoded_result, dict):
                unknown = True
                continue
            result = cast(dict[str, Any], decoded_result)
            if not isinstance(result.get("content"), list):
                unknown = True
                continue
            decoded_details = result.get("details", {})
            details = cast(dict[str, Any], decoded_details) if isinstance(decoded_details, dict) else {}
            resolved_path = details.get("resolvedPath")
            resolved = (_frozen_path(resolved_path, cwd) if isinstance(resolved_path, str)
                        else _uri_path(requested, files) if "://" in requested else _frozen_path(requested, cwd))
            if resolved is not None and resolved in files:
                reads.add(resolved)
    return reads, fired, unknown or bool(pending) or not complete


def _target_exposure(target: str, files: set[str], reads: set[str], fired: set[str]) -> bool:
    user = target.startswith("user-")
    raw = target.removeprefix("user-")
    if raw == "all":
        selected = [p for p in files if p.startswith(USER_ROOT) == user]
    else:
        roots = target_paths(target)
        selected = [p for p in files if any(p == root or p.startswith(root.rstrip("/") + "/") for root in roots)]
    if raw.startswith("file:") or raw == "all":
        if any(PurePosixPath(p).name in {"AGENTS.md", "RULES.md"} for p in selected):
            return True
    return any(p in reads or (raw.startswith("rule:") or raw == "all") and p in fired for p in selected)


def artifact_exposure(directory: Path, artifacts: Mapping[str, str], targets: Sequence[str]) -> bool | None:
    """Any selected target exposed; absent or malformed frozen evidence is unknown.

    The baseline is the arm's materialized mapping, not the seed or live guidance.
    Runner-reported exposure and case relevance tags are deliberately not inputs.
    """
    if not targets:
        return None
    for target in targets:
        validate_target(target)
    try:
        baseline = artifacts.get("baseline-guidance.json")
        events = artifacts.get("events.jsonl")
        if baseline is None or events is None:
            return None
        decoded: object = json.loads((directory / baseline).read_text())
        if not isinstance(decoded, dict):
            return None
        files: set[str] = set()
        for key, value in cast(dict[object, object], decoded).items():
            if not isinstance(key, str) or not isinstance(value, str):
                return None
            relative_path(key)
            base64.b64decode(value, validate=True)
            files.add(key)
        reads, fired, unknown = _events(directory / events, files)
    except (OSError, ValueError):
        return None
    if any(_target_exposure(target, files, reads, fired) for target in targets):
        return True
    return None if unknown else False
