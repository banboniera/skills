from pathlib import Path
import pytest

from guidance_evals import runtime
from guidance_evals.cli import main
from guidance_evals.contracts import Agent, Image, Project
from guidance_evals.dispatcher import Dispatcher
from guidance_evals.identity import IdentityInputs
from guidance_evals.runner import GradeResult, GradedCheck, TrialResult, TrialSpec
from guidance_evals.sandbox import Sandbox, SeedInfo
from guidance_evals.store import Store


class PolicyRunner(runtime.RealRunner):
    def __init__(self, root: Path, *, failure: str | None = None) -> None:
        project = Project(slug="policy", image=Image(containerfile="Containerfile"),
                          agent=Agent(roles={"default": "test/paid"}, max_cost=1.5))
        store = Store(root / "store")
        super().__init__(root, project, store, Dispatcher(root / "dispatcher"),
                         Sandbox(root, project, store.root, "policy"), SeedInfo("image", root, "snapshot"), {})
        self.started: list[str] = []
        self.failure = failure

    def run_trial(self, trial: TrialSpec, *, readonly: bool = False) -> TrialResult:
        self.started.append(trial.id)
        if self.failure:
            return TrialResult(status="infra_error", error=self.failure, cost=0.0017)
        return TrialResult(status="complete", cost=0.8)

    def grade(self, trial: object) -> GradeResult:
        return GradeResult(checks=[GradedCheck(id="completion", passed=True)])


def specs(root: Path, count: int) -> list[TrialSpec]:
    case = root / "case"
    case.mkdir()
    (case / "case.toml").write_text('id="case"\nprompt="Work"\ntargets=["all"]\n[budget]\nmax_cost=1.5\n')
    return [TrialSpec(identity=IdentityInputs(snapshot="s", arm="a", case=str(i), agent="g", engine="e", replicate=0),
                      arm="current", case_key=f"family-{i}/case", family=f"family-{i}", targets=["all"], case_dir=str(case))
            for i in range(count)]


def test_paid_run_requires_user_budget_before_preparing_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", str(tmp_path / "experiment.toml"), "--project", str(tmp_path)]) == 2
    error = capsys.readouterr().err.lower()
    assert "budget" in error and "user" in error


def test_paid_triggers_require_user_budget(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["triggers", "some-skill", "--project", str(tmp_path)]) == 2
    error = capsys.readouterr().err.lower()
    assert "budget" in error and "user" in error


def test_triggers_stop_on_measured_spend_and_report_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from guidance_evals import commands

    class TriggerRunner(PolicyRunner):
        def run_trial(self, trial: TrialSpec, *, readonly: bool = False) -> TrialResult:
            self.started.append(trial.id)
            return TrialResult(status="complete", cost=0.04)

    def no_events(_path: Path) -> dict[str, list[dict[str, str]]]:
        return {"commands": []}

    def never_loaded(_commands: object, _skill: str, _window: int) -> bool:
        return False

    monkeypatch.setattr(commands, "extract_events", no_events)
    monkeypatch.setattr(commands, "skill_loaded", never_loaded)
    triggers = tmp_path / ".omp/evals/triggers"
    triggers.mkdir(parents=True)
    (triggers / "skill.toml").write_text('skill = "skill"\nshould = ["a", "b", "c"]\nshould_not = ["d", "e", "f"]\n')
    runner = TriggerRunner(tmp_path)
    report = commands.measure_triggers(runner, "skill", 0.12)
    # Caps are $0.05 per trial: 0 + .05 and .04 + .05 fit; .08 + .05 exceeds $0.12.
    assert len(runner.started) == 2
    assert report["complete"] is False and report["stop_reason"] == "budget"
    assert report["recall"] is None and report["false_positive_rate"] is None
    assert abs(report["spent"] - 0.08) < 1e-9


def test_run_budget_reserves_running_trial_caps_and_reports_actual_spend(tmp_path: Path) -> None:
    runner = PolicyRunner(tmp_path)
    planned = specs(tmp_path, 5)
    budget = runtime.RunBudget(3.0)
    summary = runner.execute(planned, jobs=4, budget=budget)
    assert len(runner.started) == 2
    assert summary.stop_reason == "budget"
    assert len(summary.scheduled_ids) == 2
    assert budget.spent == 1.6


def test_first_wave_common_infrastructure_failure_stops_remaining_trials(tmp_path: Path) -> None:
    runner = PolicyRunner(tmp_path, failure="dispatcher 429 Budget exhausted")
    planned = specs(tmp_path, 36)
    summary = runner.execute(planned, jobs=3, budget=runtime.RunBudget(20))
    assert len(runner.started) == 3
    assert summary.stop_reason == "first-wave-infra"
    assert summary.infra_errors == {"dispatcher 429 Budget exhausted": 3}


def test_resume_counts_prior_spend_without_restarting_completed_trials(tmp_path: Path) -> None:
    runner = PolicyRunner(tmp_path)
    planned = specs(tmp_path, 4)
    runner.store.save_trial(planned[0], TrialResult(status="complete", cost=0.8))
    budget = runtime.RunBudget(2.0)
    summary = runner.execute(planned, jobs=3, budget=budget)
    assert runner.started == []
    assert summary.stop_reason == "budget"
    assert budget.spent == 0.8


def test_dispatcher_budget_failure_has_a_safe_groupable_cause(tmp_path: Path) -> None:
    from guidance_evals.execution import extract_events
    events = tmp_path / "events.jsonl"
    events.write_text('{"type":"message_end","message":{"role":"assistant","stopReason":"error","errorMessage":"429 Budget exhausted: private-detail"}}\n')
    with pytest.raises(RuntimeError, match="dispatcher 429 Budget exhausted") as error:
        extract_events(events)
    assert "private-detail" not in str(error.value)


def test_unmeasured_usage_is_not_reported_as_actual_spend(tmp_path: Path) -> None:
    path = tmp_path / "usage.jsonl"
    path.write_text('{"type":"request","measured":true,"cost":0.2}\n'
                    '{"type":"request","measured":false,"cost":0.8}\n'
                    '{"type":"request","measured":false,"cost":null}\n'
                    '{"type":"revoked","cost":1.0,"unmeasured":2}\n')
    assert runtime.usage_spend([path]) == (0.2, True)


def test_infrastructure_failure_keeps_its_measured_cost(tmp_path: Path) -> None:
    from contextlib import nullcontext
    from unittest.mock import patch
    from guidance_evals.sandbox import AgentRun
    class FailedEnvironment:
        def run_agent(self, port: int, token: str, roles: dict[str, str], output: Path,
                      readonly: bool = False) -> AgentRun:
            (output / "events.jsonl").write_text(
                '{"type":"message_end","message":{"role":"assistant","stopReason":"error","errorMessage":"429 Budget exhausted"}}\n')
            return {"seconds": 0.1}
    runner = PolicyRunner(tmp_path)
    trial = specs(tmp_path, 1)[0]
    with patch.object(Dispatcher, "register", return_value="trial-token"), patch.object(
        Dispatcher, "revoke", return_value={"cost": 0.0017, "tokens": 12, "overshoot": 0, "unmeasured": 0}
    ), patch.object(Sandbox, "trial", return_value=nullcontext(FailedEnvironment())):
        result = runtime.RealRunner.run_trial(runner, trial)
    assert result.status == "infra_error"
    assert result.cost == 0.0017
    assert result.error == "dispatcher 429 Budget exhausted"


def test_unknown_spend_stops_new_trials_even_with_budget_remaining() -> None:
    budget = runtime.RunBudget(100)
    budget.record("unknown-trial", 0.2, True)
    assert not budget.admit(1.5)
    assert budget.spent == 0.2


def test_trial_failure_saves_redacted_subcommand_diagnostics(tmp_path: Path) -> None:
    from contextlib import nullcontext
    from unittest.mock import patch
    from guidance_evals.sandbox import AgentRun, SandboxError

    class FailedEnvironment:
        def run_agent(self, port: int, token: str, roles: dict[str, str], output: Path,
                      readonly: bool = False) -> AgentRun:
            raise SandboxError(f"podman run failed with exit 1: inotify_init1 exhausted; {token}")

    runner = PolicyRunner(tmp_path)
    trial = specs(tmp_path, 1)[0]
    with patch.object(Dispatcher, "register", return_value="private-trial-token"), patch.object(
        Dispatcher, "revoke", return_value={"cost": 0.0, "tokens": 0}
    ), patch.object(Sandbox, "trial", return_value=nullcontext(FailedEnvironment())):
        result = runtime.RealRunner.run_trial(runner, trial)
    assert result.status == "infra_error"
    assert result.error is not None and "podman run" in result.error
    assert "inotify_init1 exhausted" in result.error
    assert "private-trial-token" not in result.error
    diagnostic = runner.store.trial_path(trial.id) / result.artifacts["infra-error.txt"]
    assert diagnostic.read_text().strip() == result.error


def test_trial_timing_preserves_explicit_lifecycle_phases(tmp_path: Path) -> None:
    import json
    from contextlib import nullcontext
    from unittest.mock import patch

    class FinishedEnvironment:
        def run_agent(self, port: int, token: str, roles: dict[str, str], output: Path,
                      readonly: bool = False) -> dict[str, object]:
            (output / "events.jsonl").write_text('{"type":"agent_end"}\n')
            return {"seconds": 0.0, "phases": {"pod_create_seconds": 0.2, "teardown_seconds": 0.3}}

    runner = PolicyRunner(tmp_path)
    trial = specs(tmp_path, 1)[0]
    with patch.object(Dispatcher, "register", return_value="trial-token"), patch.object(
        Dispatcher, "revoke", return_value={"cost": 0.0, "tokens": 0}
    ), patch.object(Sandbox, "trial", return_value=nullcontext(FinishedEnvironment())):
        result = runtime.RealRunner.run_trial(runner, trial)
    assert result.status == "complete"
    timing = json.loads((runner.store.trial_path(trial.id) / "timing.json").read_text())
    assert timing["phases"] == {"pod_create_seconds": 0.2, "teardown_seconds": 0.3}
    assert timing["overhead_seconds"] == timing["trial_seconds"] - timing["agent_seconds"]
