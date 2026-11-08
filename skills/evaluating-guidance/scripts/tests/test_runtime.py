from pathlib import Path
import subprocess

import pytest

from guidance_evals.runtime import capture_snapshot, guidance_files


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def test_snapshot_captures_changes_without_mutating_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "--quiet")
    (source / "file.py").write_text("before\n")
    git(source, "add", "file.py")
    git(source, "-c", "user.name=Test", "-c", "user.email=test@localhost", "commit", "--quiet", "-m", "base")
    (source / "file.py").write_text("after\n")
    (source / "new.py").write_text("new\n")
    before = git(source, "status", "--porcelain")
    snapshot = capture_snapshot(source, tmp_path / "snapshots")
    assert (snapshot / "file.py").read_text() == "after\n"
    assert (snapshot / "new.py").read_text() == "new\n"
    assert git(snapshot, "remote") == ""
    assert git(source, "status", "--porcelain") == before


def test_plain_control_fixture_can_be_snapshotted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("pass\n")
    snapshot = capture_snapshot(source, tmp_path / "snapshots")
    assert git(snapshot, "rev-parse", "HEAD").strip()
    assert not (source / ".git").exists()


def test_guidance_excludes_hidden_verifiers_and_runtime_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    user_skill = home / ".omp/agent/skills/evaluating-guidance"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text("public")
    private = user_skill / "controls/answer.txt"
    private.parent.mkdir()
    private.write_text("hidden")
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    (project / "AGENTS.md").write_text("guidance")
    result = guidance_files(project)
    assert result["AGENTS.md"] == b"guidance"
    assert "HOME/.omp/agent/skills/evaluating-guidance/SKILL.md" not in result
    assert not any("controls" in key for key in result)


def test_admitted_execution_inputs_cannot_be_changed(tmp_path: Path) -> None:
    import json
    from guidance_evals.contracts import Agent, Case, DiscoveredCase, Image, Project
    from guidance_evals.dispatcher import Dispatcher
    from guidance_evals.runtime import FREE_MODEL, RealRunner, admit_cases
    from guidance_evals.sandbox import Sandbox, SeedInfo
    from guidance_evals.store import Store, atomic_write
    project = Project(slug="test", image=Image(containerfile="Containerfile"),
                      agent=Agent(roles={"default": FREE_MODEL}))
    store = Store(tmp_path / "store")
    case = DiscoveredCase(spec=Case(id="case", targets=["all"], prompt="Changed task"),
                          family="family", path=tmp_path / "case", case_hash="new")
    atomic_write(store.root / "admissions/old/admission.json", json.dumps({
        "admission_id": "old", "case": case.key, "case_hash": "old", "admitted": True}).encode())
    runner = RealRunner(tmp_path, project, store, Dispatcher(tmp_path / "dispatcher"),
        Sandbox(tmp_path, project, store.root, "run"), SeedInfo("image", tmp_path, "snapshot"), {})
    with pytest.raises(ValueError, match="execution inputs are frozen"):
        admit_cases(runner, [case], [])


def test_instrument_edits_do_not_change_captured_guidance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from guidance_evals.identity import tree_hash
    home = tmp_path / "home"
    user = home / ".omp/agent"
    instrument = user / "skills/evaluating-guidance"
    instrument.mkdir(parents=True)
    (instrument / "SKILL.md").write_text("old instrument")
    (instrument / "engine.py").write_text("old code")
    for name in ("AGENTS.md", "RULES.md", "WATCHDOG.md", "CLAUDE.md"):
        (user / name).write_text("user guidance")
    (user / "rules").mkdir()
    (user / "rules/security.md").write_text("security guidance")
    other = user / "skills/other"
    other.mkdir()
    (other / "SKILL.md").write_text("other skill")
    (other / "helper.py").write_text("other executable")
    (other / ".venv").mkdir()
    (other / ".venv/cache.py").write_text("not guidance")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    before = guidance_files(project)
    assert set(before) == {
        "HOME/.omp/agent/AGENTS.md", "HOME/.omp/agent/RULES.md",
        "HOME/.omp/agent/WATCHDOG.md", "HOME/.omp/agent/CLAUDE.md",
        "HOME/.omp/agent/rules/security.md", "HOME/.omp/agent/skills/other/SKILL.md",
        "HOME/.omp/agent/skills/other/helper.py",
    }
    (instrument / "SKILL.md").write_text("new instrument")
    (instrument / "engine.py").write_text("new code")
    assert tree_hash(guidance_files(project)) == tree_hash(before)
    (other / "SKILL.md").write_text("changed treatment")
    assert tree_hash(guidance_files(project)) != tree_hash(before)
