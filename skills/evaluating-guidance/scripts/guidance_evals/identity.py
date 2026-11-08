"""Content identity contract (all hashes are SHA-256, lowercase hex).

Canonical JSON: UTF-8, sorted object keys, compact separators, no NaN/Infinity.
Tree: sorted relative POSIX paths, permission/type modes, exact bytes (hex).
Snapshot: the entire supplied code seed including captured guidance; caller must
exclude caches/artifacts before hashing. Arm: materialized guidance only, not its
human label (identical arms share trials). Case: agent-visible case fields and seed
files only. Agent: pinned runtime execution configuration plus the execution engine
source (sandbox, guidance materialization, trial orchestration, model dispatcher),
excluding grading and policy. The whole engine is recorded for provenance only.
Trial: snapshot/arm/execution-case/agent hashes and zero-based replicate.
Grade: trial id, verifier tree, judge configuration and grading engine source.
Admission: execution case, verifier, reference patch and agent configuration.
Names and experiment membership do not identify trials. Symlinks are not followed.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import stat
from typing import Any

from pydantic import Field

from .contracts import Case, Project, StrictModel, relative_path

OMP_VERSION = "18.18.1"


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def tree_hash(files: Mapping[str, bytes], modes: Mapping[str, int] | None = None) -> str:
    modes = modes or {}
    entries = [[relative_path(path), modes.get(path, 0o644), files[path].hex()] for path in sorted(files)]
    return content_hash({"tree-v1": entries})


def directory_hash(root: Path, *, python_only: bool = False) -> str:
    files: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    for path in sorted(root.rglob("*")):
        if python_only and (path.suffix != ".py" or "__pycache__" in path.parts):
            continue
        name = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if path.is_symlink():
            files[name] = str(path.readlink()).encode()
            modes[name] = stat.S_IFLNK | stat.S_IMODE(mode)
        elif path.is_file():
            files[name] = path.read_bytes()
            modes[name] = stat.S_IMODE(mode)
    return tree_hash(files, modes)


def engine_hash() -> str:
    package = Path(__file__).parent
    dispatcher = package.parent / "dispatcher"
    files = {path.relative_to(dispatcher).as_posix(): path.read_bytes()
             for path in dispatcher.rglob("*.ts") if not path.name.endswith(".test.ts")}
    lock = package.parent / "uv.lock"
    return content_hash({"python": directory_hash(package, python_only=True),
                         "dispatcher": tree_hash(files),
                         "lock": lock.read_text() if lock.exists() else ""})


EXECUTION_SOURCES = ("arms.py", "sandbox.py", "runtime.py", "dispatcher.py")


def execution_engine_hash(package: Path | None = None) -> str:
    """Hash code that shapes what the agent sees or does; any change reruns trials."""
    package = package or Path(__file__).parent
    files = {name: (package / name).read_bytes() for name in EXECUTION_SOURCES}
    dispatcher = package.parent / "dispatcher"
    files.update({"dispatcher/" + path.name: path.read_bytes()
                  for path in dispatcher.glob("*.ts") if not path.name.endswith(".test.ts")})
    return tree_hash(files)

def grading_engine_hash() -> str:
    """Hash grading/capture dependencies, not planning, CLI or report formatting."""
    package = Path(__file__).parent
    files = {name: (package / name).read_bytes() for name in (
        "identity.py", "contracts.py", "runner.py", "store.py", "arms.py",
        "execution.py", "runtime.py", "sandbox.py", "dispatcher.py")}
    dispatcher = package.parent / "dispatcher"
    files.update({"dispatcher/" + path.name: path.read_bytes()
                  for path in dispatcher.glob("*.ts") if not path.name.endswith(".test.ts")})
    files["uv.lock"] = (package.parent / "uv.lock").read_bytes()
    return tree_hash(files)


def case_execution_hash(case: Case, root: Path) -> str:
    return content_hash({"case": case.model_dump(exclude={"family", "targets"}),
                         "seed": directory_hash(root / "seed") if case.seed == "files" else None})


def agent_hash(project: Project, image: str, roles: dict[str, str]) -> str:
    from .sandbox import render_settings
    return content_hash({"image": image, "omp": OMP_VERSION, "roles": roles,
                         "settings": render_settings(roles), "executor": execution_engine_hash(),
                         "project": project.model_dump(exclude={"judge", "protected", "blocks", "results", "slug", "image", "holdout", "smoke_model"})})


def admission_id(case_hash: str, verifier: str, reference: str, agent: str) -> str:
    return content_hash({"admission-v2": [case_hash, verifier, reference, agent]})


class IdentityInputs(StrictModel):
    snapshot: str
    arm: str
    case: str
    agent: str
    engine: str
    replicate: int = Field(ge=0)

    @property
    def trial_id(self) -> str:
        return content_hash({"trial-v2": self.model_dump(exclude={"engine"})})


def grade_id(trial_id: str, verifier_hash: str, judge_hash: str, grading_engine: str | None = None) -> str:
    return content_hash({"grade-v2": {"trial": trial_id, "verifier": verifier_hash,
                                    "judge": judge_hash, "engine": grading_engine or grading_engine_hash()}})
