from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest

from guidance_evals import sandbox as sandbox_module
from guidance_evals.contracts import Agent, Image, Project, Seed
from guidance_evals.sandbox import ResourceManifest, Sandbox, SeedInfo, TrialEnvironment


@dataclass
class WarmObservation:
    source: str
    guidance: str
    previous: dict[str, list[str]]
    files: set[str]


@dataclass
class SeedHarness:
    root: Path
    sandbox: Sandbox
    image: str = "sha256:first-image"
    observations: list[WarmObservation] = field(default_factory=list[WarmObservation])

    def snapshot(self, name: str, source: str = "first source\n") -> Path:
        snapshot = self.root / name
        snapshot.mkdir()
        (snapshot / "source.txt").write_text(source)
        (snapshot / "AGENTS.md").write_text("current guidance\n")
        # These inputs must never enter the sanitized seed or its warm-up.
        (snapshot / ".env").write_text("PRIVATE_FIXTURE=not-for-warm-up\n")
        hidden = snapshot / ".omp/evals"
        hidden.mkdir(parents=True)
        (hidden / "rubric.txt").write_text("private rubric\n")
        untrusted_cache = snapshot / "build-cache"
        untrusted_cache.mkdir()
        (untrusted_cache / "warm.json").write_text('{"sources": ["untrusted snapshot cache"]}')
        return snapshot

    def copy_snapshot(self, snapshot: Path, name: str, source: str = "second source\n") -> Path:
        destination = self.root / name
        shutil.copytree(snapshot, destination, symlinks=True)
        (destination / "source.txt").write_text(source)
        return destination


def _copy(source: Path, destination: Path) -> None:
    # Keep copies real without requiring reflink support on pytest's filesystem.
    shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)


def _metadata(seed: SeedInfo) -> dict[str, object]:
    return json.loads((seed.root / "seed.json").read_text())


def _histories(seed: SeedInfo) -> list[list[str]]:
    return [json.loads(path.read_text())["sources"]
            for path in sorted((seed.root / "caches").glob("*/warm.json"))]


@pytest.fixture
def seeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SeedHarness:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "Containerfile").write_text("FROM fixture-image\n")
    project = Project(
        slug="seed-tests", image=Image(containerfile="Containerfile"),
        agent=Agent(roles={"default": "openrouter/example:free"}),
        seed=Seed(warm=["fixture-warm"],
                  cache_dirs=["build-cache", "/home/eval/.cache/fixture"]),
    )
    harness = SeedHarness(tmp_path, Sandbox(project_root, project, tmp_path / "store", "seed-tests"))

    def unexpected_command(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError(f"unit test attempted an external command: {argv}")

    def run_warm(trial: TrialEnvironment, command: list[str], *, network: bool = False,
                 warm: bool = False, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert network is True and warm is True
        # A login shell would let /etc/profile replace the engine PATH.
        assert command[:2] == ["bash", "-c"]
        assert command[2] in trial.project.seed.warm
        source = (trial.repo / "source.txt").read_text()
        guidance = (trial.repo / "AGENTS.md").read_text()
        previous: dict[str, list[str]] = {}
        for cache in trial.project.seed.cache_dirs:
            state = trial.cache_host(cache) / "warm.json"
            history: list[str] = json.loads(state.read_text())["sources"] if state.is_file() else []
            previous[cache] = history
            state.write_text(json.dumps({"sources": [*history, source], "guidance": guidance}))
        harness.observations.append(WarmObservation(
            source, guidance, previous,
            {path.relative_to(trial.repo).as_posix() for path in trial.repo.rglob("*") if path.is_file()},
        ))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(sandbox_module, "_copy", _copy)
    monkeypatch.setattr(sandbox_module, "_command", unexpected_command)
    # Git baseline creation and MCS allocation belong to trial isolation tests;
    # retain real sanitization, hashing, guidance materialization and cache copies.
    def baseline(_repo: Path, _control: Path) -> None:
        pass

    def mcs(_manifest: ResourceManifest) -> str:
        return "s0:c1,c2"

    def local_image(_sandbox: Sandbox, _image: str) -> str:
        return harness.image

    def agent_base(_sandbox: Sandbox, _build_log: Path | None = None) -> str:
        return "fixture-agent-base"

    monkeypatch.setattr(sandbox_module, "_baseline", baseline)
    monkeypatch.setattr(sandbox_module, "_claim_mcs", mcs)
    monkeypatch.setattr(Sandbox, "_local_image", local_image)
    monkeypatch.setattr(Sandbox, "_agent_base_image", agent_base)
    def trusted_binaries(_image: str) -> None:
        pass

    monkeypatch.setattr(sandbox_module, "_check_trusted_binaries", trusted_binaries)
    monkeypatch.setattr(TrialEnvironment, "run_command", run_warm)
    return harness


def test_changed_source_derives_seed_with_new_source_and_previous_warmed_caches(seeds: SeedHarness) -> None:
    first_snapshot = seeds.snapshot("first")
    first = seeds.sandbox.prepare(first_snapshot)
    second_snapshot = seeds.copy_snapshot(first_snapshot, "second")

    second = seeds.sandbox.prepare(second_snapshot)

    assert second.root != first.root
    assert second.snapshot_hash != first.snapshot_hash
    assert second.image == first.image == "sha256:first-image"
    assert _metadata(first).get("parent_seed") is None
    assert _metadata(second)["parent_seed"] == first.root.name
    assert seeds.observations[-1].source == "second source\n"
    assert seeds.observations[-1].previous == {
        "build-cache": ["first source\n"],
        "/home/eval/.cache/fixture": ["first source\n"],
    }
    assert _histories(second) == [["first source\n", "second source\n"]] * 2
    assert _histories(first) == [["first source\n"]] * 2
    assert (second.root / "repo/source.txt").read_text() == "second source\n"


def test_derived_seed_uses_only_new_sanitized_repo_and_guidance(seeds: SeedHarness) -> None:
    first_snapshot = seeds.snapshot("first")
    (first_snapshot / "removed.txt").write_text("obsolete source\n")
    old_rule = first_snapshot / ".omp/rules/removed.md"
    old_rule.parent.mkdir(parents=True)
    old_rule.write_text("obsolete guidance\n")
    first = seeds.sandbox.prepare(first_snapshot)
    second_snapshot = seeds.copy_snapshot(first_snapshot, "second")
    (second_snapshot / "removed.txt").unlink()
    (second_snapshot / ".omp/rules/removed.md").unlink()
    (second_snapshot / "AGENTS.md").write_text("new guidance\n")

    second = seeds.sandbox.prepare(second_snapshot)

    assert _metadata(second)["parent_seed"] == first.root.name
    observed = seeds.observations[-1]
    assert observed.source == "second source\n"
    assert observed.guidance == "new guidance\n"
    assert observed.previous["build-cache"] == ["first source\n"]
    for forbidden in ("removed.txt", ".omp/rules/removed.md", ".env", ".omp/evals/rubric.txt"):
        assert forbidden not in observed.files
        assert not (second.root / "repo" / forbidden).exists()
    assert not (second.root / "repo/build-cache").exists()
    assert (second.root / "repo/AGENTS.md").read_text() == "new guidance\n"
    assert _histories(second) == [["first source\n", "second source\n"]] * 2
    assert (first.root / "repo/removed.txt").read_text() == "obsolete source\n"
    assert (first.root / "repo/AGENTS.md").read_text() == "current guidance\n"


@pytest.mark.parametrize("lockfile", [
    "Cargo.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock",
    "bun.lockb", "uv.lock", "poetry.lock", "go.sum",
])
def test_dependency_lock_change_requires_full_seed(seeds: SeedHarness, lockfile: str) -> None:
    first_snapshot = seeds.snapshot("first")
    (first_snapshot / lockfile).write_bytes(b"dependency version 1\n")
    first = seeds.sandbox.prepare(first_snapshot)
    second_snapshot = seeds.copy_snapshot(first_snapshot, "second")
    (second_snapshot / lockfile).write_bytes(b"dependency version 2\n")

    second = seeds.sandbox.prepare(second_snapshot)

    assert second.root != first.root
    assert _metadata(second).get("parent_seed") is None
    assert seeds.observations[-1].source == "second source\n"
    assert all(history == [] for history in seeds.observations[-1].previous.values())
    assert _histories(second) == [["second source\n"]] * 2
    assert _histories(first) == [["first source\n"]] * 2


@pytest.mark.parametrize(("manifest", "lockfile"), [
    ("Cargo.toml", "Cargo.lock"),
    ("package.json", "package-lock.json"),
    ("pyproject.toml", "uv.lock"),
    ("go.mod", "go.sum"),
    ("Cargo.toml", None),
    ("package.json", None),
    ("pyproject.toml", None),
    ("requirements.txt", None),
])
def test_dependency_manifest_change_requires_full_seed(
    seeds: SeedHarness, manifest: str, lockfile: str | None,
) -> None:
    first_snapshot = seeds.snapshot("first")
    (first_snapshot / manifest).write_text("first dependency configuration\n")
    if lockfile is not None:
        (first_snapshot / lockfile).write_text("unchanged dependency lock\n")
    first = seeds.sandbox.prepare(first_snapshot)
    second_snapshot = seeds.copy_snapshot(first_snapshot, "second")
    (second_snapshot / manifest).write_text("second dependency configuration\n")

    second = seeds.sandbox.prepare(second_snapshot)

    assert second.root != first.root
    assert _metadata(second).get("parent_seed") is None
    assert all(history == [] for history in seeds.observations[-1].previous.values())
    assert _histories(second) == [["second source\n"]] * 2


def test_changed_resolved_image_requires_full_seed(seeds: SeedHarness) -> None:
    first_snapshot = seeds.snapshot("first")
    first = seeds.sandbox.prepare(first_snapshot)
    second_snapshot = seeds.copy_snapshot(first_snapshot, "second")
    seeds.image = "sha256:second-image"

    second = seeds.sandbox.prepare(second_snapshot)

    assert first.image == "sha256:first-image"
    assert second.image == "sha256:second-image"
    assert _metadata(second).get("parent_seed") is None
    assert all(history == [] for history in seeds.observations[-1].previous.values())
    assert _histories(second) == [["second source\n"]] * 2


@pytest.mark.parametrize("changed_config", ["warm", "cache_dirs", "env"])
def test_changed_project_seed_configuration_requires_full_seed(
    seeds: SeedHarness, changed_config: str,
) -> None:
    first_snapshot = seeds.snapshot("first")
    first = seeds.sandbox.prepare(first_snapshot)
    second_snapshot = seeds.copy_snapshot(first_snapshot, "second")
    project = seeds.sandbox.project.model_copy(deep=True)
    if changed_config == "warm":
        project.seed.warm = ["fixture-warm --different-mode"]
    elif changed_config == "cache_dirs":
        project.seed.cache_dirs.append("extra-cache")
    else:
        project.env["BUILD_MODE"] = "different-mode"
    seeds.sandbox.project = project

    second = seeds.sandbox.prepare(second_snapshot)

    assert second.root != first.root
    assert _metadata(second).get("parent_seed") is None
    assert all(history == [] for history in seeds.observations[-1].previous.values())
    assert _histories(second) == [["second source\n"]] * len(project.seed.cache_dirs)
    assert _histories(first) == [["first source\n"]] * 2


def test_identical_sanitized_snapshot_reuses_seed_without_warm(seeds: SeedHarness) -> None:
    first_snapshot = seeds.snapshot("first")
    first = seeds.sandbox.prepare(first_snapshot)
    seed_metadata = (first.root / "seed.json").read_bytes()
    same_snapshot = seeds.copy_snapshot(first_snapshot, "same", source="first source\n")
    # Neither hidden secrets nor excluded scratch cache content changes identity.
    (same_snapshot / ".env").write_text("PRIVATE_FIXTURE=changed\n")
    (same_snapshot / "build-cache/warm.json").write_text('{"sources": ["different untrusted cache"]}')

    def forbidden_warm(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError("an unchanged sanitized snapshot must not execute warm commands")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(TrialEnvironment, "run_command", forbidden_warm)
        reused = seeds.sandbox.prepare(same_snapshot)

    assert reused == first
    assert (reused.root / "seed.json").read_bytes() == seed_metadata
    assert _histories(reused) == [["first source\n"]] * 2
    assert [path for path in (seeds.sandbox.store_root / "seeds").iterdir()] == [first.root]


def test_exact_snapshot_reuse_takes_precedence_over_compatible_parent(seeds: SeedHarness) -> None:
    first_snapshot = seeds.snapshot("first")
    first = seeds.sandbox.prepare(first_snapshot)
    second_snapshot = seeds.copy_snapshot(first_snapshot, "second")
    second = seeds.sandbox.prepare(second_snapshot)

    def forbidden_warm(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise AssertionError("an existing exact seed must win over an incremental parent")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(TrialEnvironment, "run_command", forbidden_warm)
        reused_first = seeds.sandbox.prepare(first_snapshot)
        reused_second = seeds.sandbox.prepare(second_snapshot)

    assert reused_first == first
    assert reused_second == second
    assert _histories(first) == [["first source\n"]] * 2
    assert _histories(second) == [["first source\n", "second source\n"]] * 2
    assert _metadata(second)["parent_seed"] == first.root.name


def test_incremental_warm_removes_obsolete_cache_files(
    seeds: SeedHarness, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_snapshot = seeds.snapshot("first")
    first = seeds.sandbox.prepare(first_snapshot)
    for cache in (first.root / "caches").iterdir():
        (cache / "obsolete").write_text("stale build output")
    run_warm = TrialEnvironment.run_command

    def remove_obsolete(trial: TrialEnvironment, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        result = run_warm(trial, command, **kwargs)
        for cache in trial.project.seed.cache_dirs:
            obsolete = trial.cache_host(cache) / "obsolete"
            if obsolete.exists():
                obsolete.unlink()
        return result

    monkeypatch.setattr(TrialEnvironment, "run_command", remove_obsolete)
    second = seeds.sandbox.prepare(seeds.copy_snapshot(first_snapshot, "second"))
    assert not list((second.root / "caches").glob("*/obsolete"))
    assert len(list((first.root / "caches").glob("*/obsolete"))) == 2
