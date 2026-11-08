from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, cast

import pytest

from guidance_evals.admission_status import admission_status as status
from guidance_evals.contracts import Agent, Image, Project, discover_cases
from guidance_evals.identity import admission_id, agent_hash, content_hash, directory_hash
from guidance_evals.sandbox import Sandbox, SandboxError
from guidance_evals.store import Store


class LocalImages:
    def __init__(self) -> None:
        self.digest: str | None = "a" * 64
        self.context_hashes: list[str] = []
        self.contexts: set[Path] = set()
        self.failure = False

    def inspect(self, argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert argv[:2] == ["podman", "images"], "status must only inspect local images"
        assert "label=guidance-evals.project=status" in argv
        self.context_hashes.append(argv[-1].removeprefix("label=guidance-evals.context="))
        self.contexts.update(Path(tempfile.gettempdir()).glob("guidance-evals-image-*"))
        if self.failure:
            return subprocess.CompletedProcess(argv, 125, b"", b"private diagnostics")
        output = ("sha256:" + self.digest + "\n").encode() if self.digest is not None else b""
        return subprocess.CompletedProcess(argv, 0, output, b"")


@pytest.fixture
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Project, Store, LocalImages]:
    root = tmp_path / "project"
    case = root / ".omp/evals/cases/family/example"
    (case / "verifier").mkdir(parents=True)
    (case / "case.toml").write_text('id="example"\ntargets=["all"]\nprompt="Fix the bug."\n')
    (case / "verifier/verify.sh").write_text("exit 0\n")
    (case / "reference.patch").write_text("reference patch\n")
    (root / ".omp/evals/Containerfile").write_text("FROM scratch\n")
    context = root / ".omp/evals/image"
    context.mkdir()
    (context / "tool").write_text("tool bytes\n")
    (context / "tool").chmod(0o644)
    project = Project(slug="status", image=Image(containerfile="Containerfile", context="image"),
                      agent=Agent(roles={"default": "provider/model"}))
    store = Store(tmp_path / "store")
    images = LocalImages()
    monkeypatch.setattr("guidance_evals.sandbox._command", images.inspect)
    def agent_base(_sandbox: Sandbox, _build_log: Path | None = None) -> str:
        return "c" * 64

    monkeypatch.setattr(Sandbox, "_agent_base_image", agent_base)
    return root, project, store, images


def save_admission(root: Path, project: Project, store: Store, image: str) -> dict[str, Any]:
    case = discover_cases(root, project)[0]
    verifier = directory_hash(case.path / "verifier")
    reference = content_hash((case.path / "reference.patch").read_bytes().hex())
    agent = agent_hash(project, image, project.agent.roles)
    ident = admission_id(case.case_hash, verifier, reference, agent)
    record = {"case": case.key, "case_hash": case.case_hash, "verifier_hash": verifier,
              "reference_hash": reference, "agent_hash": agent, "image": image,
              "admission_id": ident, "admitted": True}
    save_record(store, ident, record)
    return record


def save_record(store: Store, ident: str, record: dict[str, Any]) -> None:
    path = store.root / "admissions" / ident / "admission.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))


def stale_entries(result: dict[str, object]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], result["stale_admissions"])


def test_matching_admissions_count_unique_current_cases(environment: tuple[Path, Project, Store, LocalImages]) -> None:
    root, project, store, images = environment
    record = save_admission(root, project, store, str(images.digest))
    save_record(store, "historical-copy", record)
    result = status(root, project, store)
    assert result["admitted"] == 1
    assert not (store.root / "seeds").exists()
    assert not (store.root / "sandboxes").exists()
    assert not (store.root / "runs").exists()


def test_matching_contents_under_wrong_directory_are_stale(
    environment: tuple[Path, Project, Store, LocalImages],
) -> None:
    root, project, store, images = environment
    record = save_admission(root, project, store, str(images.digest))
    original = store.root / "admissions" / record["admission_id"]
    original.rename(original.with_name("wrong-directory"))
    result = status(root, project, store)
    assert result["admitted"] == 0
    assert stale_entries(result) == [{"case": "family/example", "id": "wrong-directory",
                                     "reasons": ["admission storage identity mismatch"]}]


@pytest.mark.parametrize(("changed", "reason"), [
    ("prompt", "case changed"), ("seed", "case changed"),
    ("verifier", "verifier changed"), ("reference", "reference changed"),
    ("agent", "agent changed"), ("roles", "agent changed"), ("image", "image changed"),
])
def test_changed_inputs_invalidate_admission(
    environment: tuple[Path, Project, Store, LocalImages], changed: str, reason: str,
) -> None:
    root, project, store, images = environment
    case = root / ".omp/evals/cases/family/example"
    if changed == "seed":
        (case / "case.toml").write_text((case / "case.toml").read_text() + 'seed="files"\n')
        (case / "seed").mkdir()
        (case / "seed/input").write_text("before")
    record = save_admission(root, project, store, str(images.digest))
    if changed == "prompt":
        path = case / "case.toml"
        path.write_text(path.read_text().replace("Fix the bug.", "Fix a different bug."))
    elif changed == "seed":
        (case / "seed/input").write_text("after")
    elif changed == "verifier":
        (case / "verifier/verify.sh").write_text("exit 1\n")
    elif changed == "reference":
        (case / "reference.patch").write_text("new reference\n")
    elif changed == "agent":
        project.agent.max_cost = 2.0
    elif changed == "roles":
        project.agent.roles = {"default": "provider/other-model"}
    else:
        images.digest = "b" * 64
    result = status(root, project, store)
    assert result["admitted"] == 0
    stale = stale_entries(result)
    assert len(stale) == 1
    assert stale[0]["case"] == "family/example"
    assert stale[0]["id"] == record["admission_id"]
    assert reason in stale[0]["reasons"]


def test_legacy_removed_and_mismatched_ids_are_stale(environment: tuple[Path, Project, Store, LocalImages]) -> None:
    root, project, store, images = environment
    record = save_admission(root, project, store, str(images.digest))
    legacy = {"case": "family/example", "admitted": True}
    save_record(store, "legacy", legacy)
    save_record(store, "removed", {**record, "case": "family/removed"})
    save_record(store, "mismatch", {**record, "admission_id": "f" * 64})
    result = status(root, project, store)
    assert result["admitted"] == 1
    assert {entry["id"]: entry["reasons"] for entry in stale_entries(result)} == {
        "legacy": ["missing admission identity"],
        "mismatch": ["admission identity mismatch"],
        "removed": ["case missing"],
    }


@pytest.mark.parametrize("missing", ["reference.patch", "verifier"])
def test_missing_inputs_are_stale(environment: tuple[Path, Project, Store, LocalImages], missing: str) -> None:
    root, project, store, images = environment
    save_admission(root, project, store, str(images.digest))
    case = root / ".omp/evals/cases/family/example"
    path = case / missing
    if path.is_dir():
        (path / "verify.sh").unlink()
        path.rmdir()
    else:
        path.unlink()
    result = status(root, project, store)
    assert result["admitted"] == 0
    assert stale_entries(result)[0]["reasons"] == ["reference missing" if missing == "reference.patch" else "verifier missing"]


def test_missing_image_fails_closed_without_creating_execution_resources(
    environment: tuple[Path, Project, Store, LocalImages],
) -> None:
    root, project, store, images = environment
    save_admission(root, project, store, str(images.digest))
    images.digest = None
    result = status(root, project, store)
    assert result["admitted"] == 0
    assert "current image unavailable" in stale_entries(result)[0]["reasons"]
    assert not (store.root / "seeds").exists()
    assert not (store.root / "sandboxes").exists()
    assert not (store.root / "runs").exists()
    assert images.contexts and all(not path.exists() for path in images.contexts)


def test_status_image_hashes_clean_context_and_cleans_temporary_files(
    environment: tuple[Path, Project, Store, LocalImages],
) -> None:
    root, project, store, images = environment
    context = root / ".omp/evals/image"
    (context / ".env.secret").write_text("private")
    (context / "cases").mkdir()
    (context / "cases/hidden").write_text("rubric")
    sandbox = Sandbox(root, project, store.root, "status")
    assert sandbox.status_image() == images.digest
    tree = hashlib.sha256(b"tool\x00420\x00tool bytes\n\x00").hexdigest()
    digest = hashlib.sha256(b"FROM scratch\n" + tree.encode() + b"c" * 64).hexdigest()
    assert images.context_hashes == [digest]
    assert images.contexts and all(not path.exists() for path in images.contexts)
    (context / "tool").write_text("changed\n")
    sandbox.status_image()
    assert images.context_hashes[-1] != images.context_hashes[0]
    (root / ".omp/evals/Containerfile").write_text("FROM changed\n")
    previous = images.context_hashes[-1]
    sandbox.status_image()
    assert images.context_hashes[-1] != previous


def test_status_image_inspection_error_is_short_and_cleans_context(
    environment: tuple[Path, Project, Store, LocalImages],
) -> None:
    root, project, store, images = environment
    images.failure = True
    with pytest.raises(SandboxError, match="^cannot inspect agent image$"):
        Sandbox(root, project, store.root, "status").status_image()
    assert images.contexts and all(not path.exists() for path in images.contexts)


def test_status_image_rejects_context_outside_project(
    environment: tuple[Path, Project, Store, LocalImages],
) -> None:
    root, project, store, _images = environment
    project.image.context = "../../.."
    with pytest.raises(SandboxError, match="image inputs must remain in project"):
        Sandbox(root, project, store.root, "status").status_image()
