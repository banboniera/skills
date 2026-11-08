"""Pure guidance treatments. HOME/ is a virtual root, not the host HOME.

Keys are project-relative POSIX paths or HOME/.omp/agent/... for clean sandbox
user guidance. `none` removes project guidance; `minus:user-all` removes user
only. Ref guidance is the complete replacement set, including user guidance if
wanted. Never reads the host filesystem or resolves git refs.
"""
from collections.abc import Mapping
from pathlib import PurePosixPath
import re

from .contracts import relative_path, validate_target

USER_ROOT = "HOME/.omp/agent/"


def is_guidance(path: str) -> bool:
    relative_path(path)
    if path.startswith(USER_ROOT):
        rest = path.removeprefix(USER_ROOT)
        return rest in {"AGENTS.md", "RULES.md", "WATCHDOG.md", "CLAUDE.md"} or rest.startswith(("rules/", "skills/"))
    if path.startswith("HOME/"):
        return False
    return (PurePosixPath(path).name in {"AGENTS.md", "CLAUDE.md"}
            or path in {".omp/RULES.md", ".omp/WATCHDOG.md"}
            or path.startswith((".omp/rules/", ".omp/skills/")))


def target_paths(target: str) -> list[str]:
    validate_target(target)
    user = target.startswith("user-")
    target = target.removeprefix("user-")
    root = USER_ROOT if user else ".omp/"
    if target == "all":
        return [USER_ROOT] if user else ["AGENTS.md", "CLAUDE.md", ".omp/RULES.md", ".omp/WATCHDOG.md", ".omp/rules", ".omp/skills"]
    kind, _, name = target.partition(":")
    if kind == "rule":
        return [f"{root}rules/{name}.md"]
    if kind == "skill":
        return [f"{root}skills/{name}"]
    return [USER_ROOT + name if user else name]


def remove_index_rows(content: bytes, target: str) -> bytes:
    kind, _, name = target.removeprefix("user-").partition(":")
    if kind not in {"rule", "skill"}:
        return content
    link = re.compile(rf"{kind}://{re.escape(name)}(?![\w-])")
    return "".join(line for line in content.decode("utf-8").splitlines(keepends=True) if not link.search(line)).encode("utf-8")


def materialize(seed: Mapping[str, bytes], arm: str,
                ref_files: Mapping[str, bytes] | None = None, *,
                blocks: Mapping[str, list[str]] | None = None) -> dict[str, bytes]:
    files = {path: data for path, data in seed.items() if is_guidance(path)}
    if arm == "current":
        return files
    if arm.startswith("ref:") and arm[4:]:
        if ref_files is None:
            raise ValueError("ref arm requires resolved guidance files")
        return {path: data for path, data in ref_files.items() if is_guidance(path)}
    if arm == "none":
        return {p: v for p, v in files.items() if p.startswith(USER_ROOT)}
    if not arm.startswith("minus:"):
        raise ValueError("expected current, ref:<rev>, minus:<target> or none")
    raw_target = arm.removeprefix("minus:")
    if blocks is not None and raw_target in blocks:
        for target in blocks[raw_target]:
            files = materialize(files, f"minus:{validate_target(target)}")
        return files
    paths = target_paths(raw_target)
    user = raw_target.startswith("user-")
    for path in list(files):
        if path.startswith(USER_ROOT) != user:
            continue
        if raw_target in {"all", "user-all"} or any(path == p or path.startswith(p.rstrip("/") + "/") for p in paths):
            del files[path]
        elif PurePosixPath(path).name in {"AGENTS.md", "CLAUDE.md", "RULES.md", "WATCHDOG.md"}:
            files[path] = remove_index_rows(files[path], raw_target)
    return files
