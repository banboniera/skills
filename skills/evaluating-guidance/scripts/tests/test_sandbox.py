from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from guidance_evals.arms import materialize
from guidance_evals.contracts import Agent, Case, Image, Project
from guidance_evals.sandbox import (
    ResourceManifest, Sandbox, SandboxError, SeedInfo, TrialEnvironment, janitor,
    parse_recorder_log, render_settings,
)


def test_settings_disable_inherited_features_and_fallbacks() -> None:
    settings = json.loads(render_settings({"default": "openrouter/example:free"}))
    assert settings["memory"]["backend"] == "off"
    assert settings["advisor"]["enabled"] is False
    assert settings["archive"]["enabled"] is False
    assert settings["autolearn"]["enabled"] is False
    assert settings["dev"]["autoqa"] is False
    assert settings["retry"]["modelFallback"] is False
    assert settings["retry"]["fallbackChains"]["default"] == []
    assert settings["modelRoles"]["task"] == "openrouter/example:free"


def test_settings_require_explicit_default_role() -> None:
    with pytest.raises(ValueError, match="default"):
        render_settings({"task": "openrouter/example:free"})


def test_recorder_parser_reports_denials_without_recording_arguments() -> None:
    text = '\n'.join([json.dumps({"command": "git", "denied": True}),
                      json.dumps({"command": "psql", "denied": False})])
    result = parse_recorder_log(text)
    assert result["denied"] == 1
    assert result["valid"] is True
    assert result["commands"] == [{"command": "git", "denied": True},
                                  {"command": "psql", "denied": False}]


def test_recorder_parser_fails_closed_on_damaged_or_missing_records() -> None:
    assert parse_recorder_log("not json")["valid"] is False
    assert parse_recorder_log('{"command":"git","denied":"false"}')["valid"] is False
    assert parse_recorder_log("")["denied"] == 0


def test_manifest_records_before_launch_and_tears_down_in_reverse(tmp_path: Path) -> None:
    manifest = ResourceManifest(tmp_path / "resources.json", "run-a")
    manifest.add("pod", "ge-pod")
    manifest.add("container", "ge-relay")
    saved = json.loads(manifest.path.read_text())
    assert saved["owner"] == "run-a"
    assert saved["resources"][0]["name"] == "ge-pod"
    with patch("guidance_evals.sandbox._owned", return_value=True), patch(
        "guidance_evals.sandbox._command"
    ) as command:
        command.return_value.returncode = 0
        manifest.cleanup()
    assert command.call_args_list[0].args[0] == ["podman", "rm", "--force", "--time", "0", "ge-relay"]
    assert command.call_args_list[1].args[0] == ["podman", "pod", "rm", "--force", "--time", "0", "ge-pod"]
    assert json.loads(manifest.path.read_text())["state"] == "cleaned"


def test_manifest_never_removes_foreign_resource(tmp_path: Path) -> None:
    manifest = ResourceManifest(tmp_path / "resources.json", "run-a")
    manifest.add("container", "ge-reused-name")
    with patch("guidance_evals.sandbox._owned", return_value=False), patch(
        "guidance_evals.sandbox._command"
    ) as command:
        manifest.cleanup()
    command.assert_not_called()


def _trial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
           guidance: dict[str, bytes] | None = None) -> TrialEnvironment:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    seed_root = tmp_path / "seed"
    rules = seed_root / "repo/.omp/rules"
    rules.mkdir(parents=True)
    (rules / "keep.md").write_text("Keep this rule.\n")
    (seed_root / "repo/AGENTS.md").write_text("- [keep](rule://keep)\n")
    project = Project(slug="sandbox", image=Image(containerfile="Containerfile"),
                      agent=Agent(roles={"default": "openrouter/example:free"}))
    sandbox = Sandbox(tmp_path / "project", project, tmp_path / "store", "test-run")
    return TrialEnvironment(sandbox, SeedInfo("image", seed_root, "hash"), "trial",
                            Case(id="example", targets=["rule:keep"], prompt="Do work."),
                            tmp_path, guidance)


def _prepare_without_pod(trial: TrialEnvironment) -> None:
    def copy(source: Path, destination: Path) -> None:
        shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)
    with patch("guidance_evals.sandbox._copy", side_effect=copy), patch(
        "guidance_evals.sandbox._baseline"
    ):
        trial.prepare(warm=True)


def test_resolved_empty_guidance_replaces_original_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trial = _trial(tmp_path, monkeypatch, guidance={})
    try:
        _prepare_without_pod(trial)
        assert not (trial.repo / "AGENTS.md").exists()
        assert not (trial.repo / ".omp/rules/keep.md").exists()
    finally:
        trial.manifest.cleanup()


def test_minus_arm_removes_rule_and_index_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed = {".omp/rules/keep.md": b"Keep this rule.\n", "AGENTS.md": b"- [keep](rule://keep)\n"}
    trial = _trial(tmp_path, monkeypatch, guidance=materialize(seed, "minus:rule:keep"))
    try:
        _prepare_without_pod(trial)
        assert not (trial.repo / ".omp/rules/keep.md").exists()
        assert (trial.repo / "AGENTS.md").read_text() == ""
    finally:
        trial.manifest.cleanup()


def test_user_guidance_is_materialized_only_in_clean_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trial = _trial(tmp_path, monkeypatch, guidance={"HOME/.omp/agent/RULES.md": b"user rule"})
    try:
        _prepare_without_pod(trial)
        assert (trial.home / ".omp/agent/RULES.md").read_bytes() == b"user rule"
        assert not (trial.repo / "HOME").exists()
        assert not (trial.home / ".ssh").exists()
    finally:
        trial.manifest.cleanup()


def test_teardown_removes_scratch_but_preserves_artifacts(tmp_path: Path) -> None:
    manifest = ResourceManifest(tmp_path / "resources.json", "run-a")
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo/scratch").write_text("discard")
    (tmp_path / "events.jsonl").write_text("retained")
    manifest.cleanup()
    assert not (tmp_path / "repo").exists()
    assert (tmp_path / "events.jsonl").read_text() == "retained"


def test_janitor_preserves_live_owners_and_reaps_dead_ones(tmp_path: Path) -> None:
    live = ResourceManifest(tmp_path / "sandboxes/live/resources.json", "live")
    dead = ResourceManifest(tmp_path / "sandboxes/dead/resources.json", "dead")
    data = json.loads(dead.path.read_text())
    data["pid"] = 2147483647
    data["process_start"] = "not-alive"
    dead.path.write_text(json.dumps(data))
    assert janitor(tmp_path) == {"cleaned": 1, "active": 1}
    assert json.loads(live.path.read_text())["state"] == "active"
    assert json.loads(dead.path.read_text())["state"] == "cleaned"


def test_concurrent_trials_cannot_share_mcs_even_on_random_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with patch("guidance_evals.sandbox.secrets.SystemRandom") as random:
        random.return_value.sample.side_effect = [[1, 2], [1, 2], [3, 4]]
        first = _trial(tmp_path, monkeypatch)
        second = TrialEnvironment(first.sandbox, first.seed, "second", first.case, tmp_path, None)
    try:
        assert first.mcs == "s0:c1,c2"
        assert second.mcs == "s0:c3,c4"
        second.manifest.cleanup()
        reservation = tmp_path / f"guidance-evals-mcs-{os.getuid()}" / first.mcs
        assert reservation.read_text() == str(first.manifest.path)
    finally:
        first.manifest.cleanup()
        second.manifest.cleanup()


def test_failed_teardown_preserves_mcs_until_containers_are_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    trial = _trial(tmp_path, monkeypatch)
    trial.manifest.add("container", "ge-failed")
    reservation = tmp_path / f"guidance-evals-mcs-{os.getuid()}" / trial.mcs
    with patch("guidance_evals.sandbox._owned", return_value=True), patch(
        "guidance_evals.sandbox._command"
    ) as command:
        command.return_value.returncode = 1
        with pytest.raises(SandboxError, match="teardown failed"):
            trial.manifest.cleanup()
    assert reservation.is_file()
    assert json.loads(trial.manifest.path.read_text())["state"] == "cleanup_failed"
    with patch("guidance_evals.sandbox._owned", return_value=False):
        trial.manifest.cleanup()
    assert not reservation.exists()


def test_command_failure_keeps_subcommand_and_redacts_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess
    trial = _trial(tmp_path, monkeypatch)
    _prepare_without_pod(trial)
    secret = "fixture-secret-not-for-errors"
    stderr = (
        f"Error: inotify_init1: Too many open files\nFIXTURE_PASSWORD={secret}\n"
        "Bearer private-bearer-value\nhttps://private.invalid/path?token=private-query\n"
    ).encode()
    result = subprocess.CompletedProcess([], 1, b"", stderr)
    try:
        with patch("guidance_evals.sandbox.subprocess.run", return_value=result):
            with pytest.raises(SandboxError) as captured:
                trial.run_command(["true"], extra_env={"FIXTURE_PASSWORD": secret})
    finally:
        with patch("guidance_evals.sandbox._owned", return_value=False):
            trial.manifest.cleanup()
    message = str(captured.value)
    assert "podman run" in message
    assert "inotify_init1: Too many open files" in message
    assert secret not in message
    assert "private-bearer-value" not in message
    assert "private-query" not in message
    assert "/control" not in message


def test_preflight_readiness_does_not_require_inotify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess
    import sys
    trial = _trial(tmp_path, monkeypatch)
    _prepare_without_pod(trial)
    captured: list[str] = []

    class ProbeCaptured(Exception):
        pass

    def relays(_port: int) -> Path:
        gateway, recorder = trial.root / "gateway", trial.root / "recorder"
        gateway.mkdir()
        recorder.mkdir()
        return recorder

    def command(argv: list[str], **_kwargs: object) -> None:
        captured.append(argv[2])
        raise ProbeCaptured

    monkeypatch.setattr(trial, "_relays", relays)
    monkeypatch.setattr(trial, "run_command", command)
    try:
        with pytest.raises(ProbeCaptured):
            trial.run_agent(12345, "trial-token", {"default": "local/test"}, tmp_path / "artifacts")
    finally:
        trial.manifest.cleanup()
    # Exhausted host inotify must not stop an otherwise ready isolated pod.
    setup = """
import ctypes, os, socket
def exhausted(*args, **kwargs):
    raise OSError(24, 'inotify instances exhausted')
ctypes.CDLL = exhausted
os.path.exists = lambda path: path in {'/gateway/model.sock', '/recorder/ready'}
class DeniedSocket:
    def settimeout(self, value): pass
    def connect_ex(self, address): return 111
    def close(self): pass
socket.socket = DeniedSocket
"""
    result = subprocess.run([sys.executable, "-c", setup + captured[0]], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["external_connect_denied"] is True


def test_seed_hiding_covers_ancestors_secrets_and_patterns() -> None:
    from guidance_evals.sandbox import hidden_from_seed, seed_patterns
    patterns = seed_patterns(["notes/*.txt", ".env*"], ["target"])
    assert hidden_from_seed(".omp/evals/cases/a/case.toml", patterns)
    assert hidden_from_seed("target/debug/x", patterns)
    assert hidden_from_seed("notes/excerpt.txt", patterns)
    assert hidden_from_seed("config/.env.local", patterns)
    assert hidden_from_seed("home/.ssh/id", patterns)
    assert not hidden_from_seed("session-excerpt.txt", patterns)
    assert not hidden_from_seed("src/app.py", patterns)


def test_untracked_files_visible_to_the_agent_are_reported(tmp_path: Path) -> None:
    import subprocess
    from guidance_evals.commands import untracked_in_seed
    from guidance_evals.contracts import Agent, Image, Project
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / "session-excerpt.txt").write_text("answer")
    (tmp_path / ".omp/evals").mkdir(parents=True)
    (tmp_path / ".omp/evals/notes.txt").write_text("hidden")
    (tmp_path / "secret.txt").write_text("hidden")
    project = Project(slug="p", image=Image(containerfile="Containerfile"), hide=[".omp/evals", "secret.txt"],
                      agent=Agent(roles={"default": "local/test"}))
    assert untracked_in_seed(tmp_path, project) == ["session-excerpt.txt"]
