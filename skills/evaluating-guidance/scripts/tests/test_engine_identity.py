from pathlib import Path

import pytest

from guidance_evals import identity


def test_dispatcher_source_and_runtime_lock_affect_engine_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "guidance_evals"
    package.mkdir()
    source = package / "identity.py"
    source.write_text("engine")
    monkeypatch.setattr(identity, "__file__", str(source))
    dispatcher = tmp_path / "dispatcher"
    dispatcher.mkdir()
    entry = dispatcher / "server.ts"
    entry.write_text("first")
    first = identity.engine_hash()
    entry.write_text("second")
    assert identity.engine_hash() != first
    second = identity.engine_hash()
    (tmp_path / "uv.lock").write_text("locked runtime")
    assert identity.engine_hash() != second


def test_grading_identity_excludes_cli_and_report_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    package = tmp_path / "guidance_evals"
    shutil.copytree(Path(identity.__file__).parent, package)
    (tmp_path / "dispatcher").mkdir()
    (tmp_path / "uv.lock").write_text("runtime")
    monkeypatch.setattr(identity, "__file__", str(package / "identity.py"))
    before = identity.grading_engine_hash()
    (package / "report.py").write_text("new report layout")
    (package / "cli.py").write_text("new help")
    assert identity.grading_engine_hash() == before
    (package / "execution.py").write_text("changed grader")
    assert identity.grading_engine_hash() != before


def test_execution_identity_changes_only_with_execution_code(tmp_path: Path) -> None:
    import shutil
    package = tmp_path / "guidance_evals"
    shutil.copytree(Path(identity.__file__).parent, package)
    dispatcher = tmp_path / "dispatcher"
    dispatcher.mkdir()
    (dispatcher / "gateway.ts").write_text("first")
    before = identity.execution_engine_hash(package)
    for grading_only in ("execution.py", "analysis.py", "report.py", "cli.py"):
        (package / grading_only).write_text("changed")
    (dispatcher / "gateway.test.ts").write_text("test only")
    assert identity.execution_engine_hash(package) == before
    for executor in ("sandbox.py", "arms.py", "runtime.py", "dispatcher.py"):
        original = (package / executor).read_text()
        (package / executor).write_text(original + "\n# changed\n")
        assert identity.execution_engine_hash(package) != before
        (package / executor).write_text(original)
    (dispatcher / "gateway.ts").write_text("second")
    assert identity.execution_engine_hash(package) != before
