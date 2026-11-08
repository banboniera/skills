from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

import pytest

from guidance_evals.contracts import Agent, Image, Project
from guidance_evals.identity import IdentityInputs, agent_hash
from guidance_evals.sandbox import ResourceManifest, Sandbox

BASE_TAG = "localhost/guidance-evals/agent-base:18.18.1"


@dataclass
class ImageEngine:
    tags: dict[str, str] = field(default_factory=dict[str, str])
    labels: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])
    builds: list[list[str]] = field(default_factory=list[list[str]])
    next_id: str = "a" * 64
    base_id: str = "c" * 64
    fail_base: bool = False
    missing_binaries: bool = False

    @property
    def project_builds(self) -> list[list[str]]:
        return [argv for argv in self.builds if argv[argv.index("--tag") + 1] != BASE_TAG]

    def command(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if argv[:3] == ["podman", "image", "exists"]:
            return subprocess.CompletedProcess(argv, int(argv[-1] not in self.tags), b"", b"")
        if argv[:3] == ["podman", "image", "inspect"]:
            return subprocess.CompletedProcess(argv, 0, self.tags[argv[-1]].encode(), b"")
        if argv[:2] == ["podman", "images"]:
            filters = [argv[index + 1].removeprefix("label=")
                       for index, argument in enumerate(argv[:-1])
                       if argument == "--filter" and argv[index + 1].startswith("label=")]
            references = [argv[index + 1].removeprefix("reference=")
                          for index, argument in enumerate(argv[:-1])
                          if argument == "--filter" and argv[index + 1].startswith("reference=")]
            matching = [ident for ident, labels in self.labels.items()
                        if all(labels.get(key) == value for key, _, value in
                               (entry.partition("=") for entry in filters))
                        and all(self.tags.get(reference) == ident for reference in references)]
            return subprocess.CompletedProcess(argv, 0,
                "\n".join("sha256:" + ident for ident in matching).encode(), b"")
        if argv[:2] == ["podman", "build"]:
            self.builds.append(argv)
            tag = argv[argv.index("--tag") + 1]
            if tag == BASE_TAG and self.fail_base:
                return subprocess.CompletedProcess(argv, 125, b"", b"fixture build failure")
            ident = self.base_id if tag == BASE_TAG else self.next_id
            self.tags[tag] = ident
            self.labels[ident] = dict(argv[index + 1].split("=", 1)
                for index, argument in enumerate(argv[:-1]) if argument == "--label")
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        if argv[:3] == ["podman", "run", "--rm"] and "--entrypoint=/bin/sh" in argv:
            return subprocess.CompletedProcess(argv, int(self.missing_binaries), b"", b"")
        raise AssertionError(f"unexpected image operation: {argv}")


@pytest.fixture
def images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Sandbox, Path, ImageEngine]:
    root = tmp_path / "project"
    base_context = tmp_path / "agent-base"
    base_context.mkdir()
    (base_context / "Containerfile.agent").write_text("FROM fixture-base\n")
    monkeypatch.setattr("guidance_evals.sandbox.AGENT_BASE_CONTEXT", base_context)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    root.mkdir()
    (root / "Containerfile").write_text("FROM fixture\nRUN omp --version\n")
    (root / "tool.txt").write_text("tool version one\n")
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "source.py").write_text("answer = 1\n")
    project = Project(slug="readable-images", image=Image(containerfile="Containerfile"),
                      agent=Agent(roles={"default": "local/test"}))
    sandbox = Sandbox(root, project, tmp_path / "store", "image-test")
    state = ImageEngine()
    monkeypatch.setattr("guidance_evals.sandbox._command", state.command)
    def baseline(_repo: Path, _control: Path) -> None:
        pass

    def mcs(_manifest: ResourceManifest) -> str:
        return "s0:c1,c2"

    def copy(source: Path, destination: Path) -> None:
        shutil.copytree(source, destination, dirs_exist_ok=True)

    monkeypatch.setattr("guidance_evals.sandbox._baseline", baseline)
    monkeypatch.setattr("guidance_evals.sandbox._claim_mcs", mcs)
    monkeypatch.setattr("guidance_evals.sandbox._copy", copy)
    return sandbox, snapshot, state


def test_same_build_inputs_reuse_readably_tagged_image(images: tuple[Sandbox, Path, ImageEngine]) -> None:
    sandbox, snapshot, state = images
    first = sandbox.prepare(snapshot)
    second = sandbox.prepare(snapshot)
    assert first == second
    assert len(state.builds) == 2
    assert len(state.project_builds) == 1
    build = state.project_builds[0]
    assert build[build.index("--build-arg") + 1] == "AGENT_IMAGE=" + "c" * 64
    tag = build[build.index("--tag") + 1]
    assert tag.startswith("localhost/guidance-evals/readable-images:18.18.1-")
    assert not re.fullmatch(r"[0-9a-f]{16,}", tag.rsplit(":", 1)[1])
    labels = state.labels[first.image]
    assert len(labels["guidance-evals.context"]) == 64
    assert labels["guidance-evals.project"] == "readable-images"
    assert sandbox.status_image() == first.image


@pytest.mark.parametrize("changed", ["Containerfile", "tool.txt"])
def test_changed_image_input_rebuilds(images: tuple[Sandbox, Path, ImageEngine], changed: str) -> None:
    sandbox, snapshot, state = images
    first = sandbox.prepare(snapshot)
    state.next_id = "b" * 64
    path = sandbox.project_root / changed
    path.write_text(path.read_text() + "changed\n")
    second = sandbox.prepare(snapshot)
    assert len(state.project_builds) == 2
    assert first.image == "a" * 64
    assert second.image == "b" * 64
    assert state.labels[first.image]["guidance-evals.context"] != state.labels[second.image]["guidance-evals.context"]


def test_trial_identity_uses_resolved_image_id_not_tag_or_context_hash(images: tuple[Sandbox, Path, ImageEngine]) -> None:
    sandbox, snapshot, state = images
    first = sandbox.prepare(snapshot)
    def identity(image: str) -> str:
        return IdentityInputs(snapshot=first.snapshot_hash, arm="arm", case="case",
            agent=agent_hash(sandbox.project, image, sandbox.project.agent.roles), engine="engine", replicate=0).trial_id
    first_id = identity(first.image)
    containerfile = sandbox.project_root / "Containerfile"
    containerfile.write_text(containerfile.read_text() + "# rebuild with identical resolved image\n")
    rebuilt = sandbox.prepare(snapshot)
    assert len(state.project_builds) == 2
    assert identity(rebuilt.image) == first_id
    state.next_id = "b" * 64
    containerfile.write_text(containerfile.read_text() + "RUN new-layer\n")
    changed = sandbox.prepare(snapshot)
    assert identity(changed.image) != first_id


def test_status_without_shared_base_is_read_only(images: tuple[Sandbox, Path, ImageEngine]) -> None:
    sandbox, _snapshot, state = images
    assert sandbox.status_image() is None
    assert state.builds == []
    assert not (sandbox.project_root.parent / "cache").exists()


def test_shared_base_is_built_once_across_projects(images: tuple[Sandbox, Path, ImageEngine]) -> None:
    sandbox, snapshot, state = images
    sandbox.prepare(snapshot)
    state.next_id = "b" * 64
    other = sandbox.project.model_copy(update={"slug": "other-project"})
    Sandbox(sandbox.project_root, other, sandbox.store_root / "other", "other").prepare(snapshot)
    assert len(state.builds) == 3
    assert len(state.project_builds) == 2
    base_build = next(argv for argv in state.builds if argv[argv.index("--tag") + 1] == BASE_TAG)
    assert not any(argument.startswith("guidance-evals.owner=") for argument in base_build)


def test_changed_base_image_invalidates_project_image(images: tuple[Sandbox, Path, ImageEngine]) -> None:
    sandbox, snapshot, state = images
    first = sandbox.prepare(snapshot)
    state.tags[BASE_TAG] = "d" * 64
    state.labels["d" * 64] = dict(state.labels["c" * 64])
    state.next_id = "b" * 64
    assert sandbox.status_image() is None
    second = sandbox.prepare(snapshot)
    assert first.image != second.image
    assert len(state.builds) == 3
    assert state.labels[first.image]["guidance-evals.context"] != state.labels[second.image]["guidance-evals.context"]


def test_changed_base_inputs_rebuild_readable_base_tag(images: tuple[Sandbox, Path, ImageEngine]) -> None:
    sandbox, snapshot, state = images
    sandbox.prepare(snapshot)
    base_context = sandbox.project_root.parent / "agent-base"
    (base_context / "Containerfile.agent").write_text("FROM changed-base\n")
    state.base_id = "d" * 64
    state.next_id = "b" * 64
    assert sandbox.status_image() is None
    assert len(state.builds) == 2
    assert sandbox.prepare(snapshot).image == "b" * 64
    assert len(state.builds) == 4
    assert state.tags[BASE_TAG] == "d" * 64


def test_failed_base_build_does_not_build_project(images: tuple[Sandbox, Path, ImageEngine]) -> None:
    sandbox, snapshot, state = images
    state.fail_base = True
    with pytest.raises(RuntimeError, match="agent base image build failed"):
        sandbox.prepare(snapshot)
    assert state.project_builds == []


def test_image_without_trusted_binaries_fails_before_any_trial(images: tuple[Sandbox, Path, ImageEngine]) -> None:
    sandbox, snapshot, state = images
    state.missing_binaries = True
    with pytest.raises(RuntimeError, match="lacks a trusted binary"):
        sandbox.prepare(snapshot)
    assert not list((sandbox.store_root / "seeds").glob("*/seed.json"))
