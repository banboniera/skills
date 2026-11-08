import base64
import json
from pathlib import Path

import pytest

from guidance_evals.cli import FrozenPlan, analyze_plan, selftest
from guidance_evals.identity import IdentityInputs
from guidance_evals.plan import Experiment
from guidance_evals.runner import GradeResult, GradedCheck, TrialResult, TrialSpec
from guidance_evals.store import Store


def read_events(path: str, *, error: bool = False) -> list[dict[str, object]]:
    return [
        {"type": "tool_execution_start", "toolCallId": "read-1", "toolName": "read", "args": {"path": path}},
        {"type": "tool_execution_end", "toolCallId": "read-1", "toolName": "read",
         "result": {"content": [{"type": "text", "text": "guidance"}]}, "isError": error},
    ]


def saved_trial(tmp_path: Path, files: list[str], events: list[dict[str, object]],
                *, legacy: bool | None = None) -> tuple[Store, TrialSpec]:
    db = Store(tmp_path)
    spec = TrialSpec(identity=IdentityInputs(snapshot="s", arm="a", case="c", agent="g", engine="e", replicate=0),
                     arm="current", case_key="f/c", family="f", targets=["rule:positive", "rule:unrelated"])
    output = db.trial_path(spec.id)
    output.mkdir(parents=True)
    (output / "baseline-guidance.json").write_text(json.dumps({p: base64.b64encode(b"guidance").decode() for p in files}))
    complete_events = [{"type": "agent_start"}, *events, {"type": "agent_end"}]
    (output / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in complete_events))
    db.save_trial(spec, TrialResult(status="complete", exposed=legacy,
        artifacts={"baseline-guidance.json": "baseline-guidance.json", "events.jsonl": "events.jsonl"}))
    if legacy is not None:
        manifest = output / "manifest.json"
        payload = json.loads(manifest.read_text())
        payload["result"]["exposed"] = legacy
        manifest.write_text(json.dumps(payload))
    db.save_grade(spec.id, "v", "j", GradeResult(checks=[GradedCheck(id="completion", passed=True)]))
    return db, spec


@pytest.mark.parametrize(("files", "events", "target", "expected"), [
    ([".omp/rules/positive.md"], [{"type": "ttsr_triggered", "rules": [{"name": "positive", "path": "/work/repo/.omp/rules/positive.md"}]}], "rule:positive", True),
    ([".omp/rules/positive.md"], [{"type": "ttsr_triggered", "rules": [{"name": "positive"}]}], "rule:positive", True),
    ([".omp/rules/positive.md"], [{"type": "ttsr_triggered", "rules": [{"name": "unrelated"}]}], "rule:positive", False),
    ([], [{"type": "ttsr_triggered", "rules": [{"name": "positive"}]}], "rule:positive", False),
    ([".omp/rules/positive.md"], read_events("rule://positive"), "rule:positive", True),
    ([".omp/rules/positive.md"], read_events("rule://positive:2-4"), "rule:positive", True),
    ([".omp/rules/positive.md"], read_events("rule://positive", error=True), "rule:positive", False),
    ([".omp/rules/positive.md", ".omp/rules/unrelated.md"], read_events("rule://unrelated"), "rule:positive", False),
    ([], read_events("rule://positive"), "rule:positive", False),
    ([".omp/skills/release/SKILL.md", ".omp/skills/release/references/cli.md"], read_events("skill://release/references/cli.md:2-4"), "skill:release", True),
    ([".omp/skills/release/SKILL.md"], read_events("skill://release"), "skill:release", True),
    ([".omp/skills/release/SKILL.md"], read_events("skill://release-other"), "skill:release", False),
    (["AGENTS.md"], [], "file:AGENTS.md", True),
    ([".omp/RULES.md"], [], "file:.omp/RULES.md", True),
    ([".omp/WATCHDOG.md"], [], "file:.omp/WATCHDOG.md", False),
    ([".omp/WATCHDOG.md"], read_events(".omp/WATCHDOG.md:3-8"), "file:.omp/WATCHDOG.md", True),
    ([], read_events("AGENTS.md"), "file:AGENTS.md", False),
    (["HOME/.omp/agent/RULES.md"], [], "user-file:RULES.md", True),
    (["HOME/.omp/agent/rules/positive.md"], read_events("rule://positive"), "user-rule:positive", True),
    ([".omp/rules/positive.md", "HOME/.omp/agent/rules/positive.md"], read_events("rule://positive"), "user-rule:positive", False),
    ([".omp/rules/positive.md"], read_events("/work/repo/.omp/rules/positive.md"), "rule:positive", True),
])
def test_target_exposure_comes_from_frozen_evidence(tmp_path: Path, files: list[str],
        events: list[dict[str, object]], target: str, expected: bool) -> None:
    db, spec = saved_trial(tmp_path, files, events, legacy=not expected)
    assert db.load_trial(spec.id).result.exposed is (not expected)
    assert db.observations(specs=[spec], exposure_targets=[target])[0].exposed is expected


@pytest.mark.parametrize("broken", ["events.jsonl", "baseline-guidance.json"])
@pytest.mark.parametrize("corrupt", [False, True])
def test_missing_or_corrupt_exposure_is_unknown(tmp_path: Path, broken: str, corrupt: bool) -> None:
    db, spec = saved_trial(tmp_path, [".omp/rules/positive.md"], [], legacy=True)
    path = db.trial_path(spec.id) / broken
    if corrupt:
        path.write_text("not json")
    else:
        path.unlink()
    assert db.observations(specs=[spec], exposure_targets=["rule:positive"])[0].exposed is None


def test_selected_members_not_case_tags_control_exposure(tmp_path: Path) -> None:
    db, spec = saved_trial(tmp_path, [".omp/rules/positive.md", ".omp/rules/unrelated.md"], read_events("rule://unrelated"), legacy=True)
    assert db.observations(specs=[spec], exposure_targets=["rule:positive", "rule:missing"])[0].exposed is False
    assert db.observations(specs=[spec], exposure_targets=["rule:positive", "rule:unrelated"])[0].exposed is True
    assert db.observations(specs=[spec])[0].exposed is None


def test_reanalysis_recomputes_exposure_without_modifying_paid_manifest(tmp_path: Path) -> None:
    db, spec = saved_trial(tmp_path, [".omp/rules/positive.md"], [], legacy=True)
    manifest = db.trial_path(spec.id) / "manifest.json"
    original = manifest.read_bytes()
    frozen = FrozenPlan(experiment=Experiment(name="read", relevant_targets=["rule:positive"]), trials=[spec])
    assert analyze_plan(db, frozen).exposure["current"].exposed == 0
    (db.trial_path(spec.id) / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in read_events("rule://positive")))
    assert analyze_plan(db, frozen).exposure["current"].exposed == 1
    assert manifest.read_bytes() == original


def test_selftest_has_frozen_exposure_without_legacy_runner_flag(tmp_path: Path) -> None:
    db = Store(tmp_path)
    frozen = selftest(db)
    result = analyze_plan(db, frozen)
    assert result.exposure["current"].exposed == 30
    assert result.exposure["none"].exposed == 0
    assert all("exposed" not in json.loads(p.read_text())["result"] for p in (tmp_path / "trials").glob("*/manifest.json"))


@pytest.mark.parametrize("end", [
    {"type": "tool_execution_end", "toolCallId": "read-1", "toolName": "read", "isError": False},
    {"type": "tool_execution_end", "toolCallId": "read-1", "toolName": "read", "result": {}},
])
def test_incomplete_success_evidence_is_unknown(tmp_path: Path, end: dict[str, object]) -> None:
    events = read_events("rule://positive")
    events[1] = end
    db, spec = saved_trial(tmp_path, [".omp/rules/positive.md"], events)
    assert db.observations(specs=[spec], exposure_targets=["rule:positive"])[0].exposed is None


def test_successful_read_in_a_nondefault_frozen_workdir(tmp_path: Path) -> None:
    events: list[dict[str, object]] = [{"type": "session", "cwd": "/workspace/custom"}, *read_events("/workspace/custom/.omp/WATCHDOG.md:2-4")]
    db, spec = saved_trial(tmp_path, [".omp/WATCHDOG.md"], events)
    assert db.observations(specs=[spec], exposure_targets=["file:.omp/WATCHDOG.md"])[0].exposed is True


def test_cli_relevance_overrides_arm_and_case_tags_for_exposure(tmp_path: Path) -> None:
    db, spec = saved_trial(tmp_path, [".omp/rules/positive.md", ".omp/rules/unrelated.md"], read_events("rule://unrelated"), legacy=True)
    frozen = FrozenPlan(experiment=Experiment(name="relevant", arms=["current", "minus:monetary"],
        relevant_targets=["rule:positive"]), trials=[spec], blocks={"monetary": ["rule:positive", "rule:unrelated"]})
    assert analyze_plan(db, frozen).exposure["current"].exposed == 0
    assert analyze_plan(db, frozen, target="monetary").exposure["current"].exposed == 1


@pytest.mark.parametrize("events", ["", '{"type":"agent_start"}\n'])
def test_empty_or_truncated_events_cannot_establish_nonexposure(tmp_path: Path, events: str) -> None:
    db, spec = saved_trial(tmp_path, [".omp/rules/positive.md"], [])
    (db.trial_path(spec.id) / "events.jsonl").write_text(events)
    assert db.observations(specs=[spec], exposure_targets=["rule:positive"])[0].exposed is None
