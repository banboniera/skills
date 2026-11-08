from pathlib import Path

import pytest

from guidance_evals.analysis import analyze, regularized_beta, success, t_quantile
from guidance_evals.arms import materialize
from guidance_evals.cli import main
from guidance_evals.contracts import Checks, ContractError, Judge, Trigger, load_json, load_toml
from guidance_evals.identity import IdentityInputs
from guidance_evals.report import markdown
from guidance_evals.runner import GradeResult, GradedCheck, Observation, TrialResult, TrialSpec
from guidance_evals.store import Store


def test_judge_trigger_and_verifier_boundaries(tmp_path: Path) -> None:
    judge = tmp_path / "judge.toml"
    judge.write_text('[[question]]\nid="question"\ncritical=false\nevidence=["diff"]\ntext="Is it safe?"\n')
    assert load_toml(judge, Judge).question[0].critical is False
    trigger = tmp_path / "trigger.toml"
    trigger.write_text('skill="example"\nshould=["yes"]\nshould_not=["no"]\nwindow=6\n')
    assert load_toml(trigger, Trigger).window == 6
    checks = tmp_path / "checks.json"
    checks.write_text('{"checks":[{"id":"completion","passed":true,"critical":true}]}')
    assert load_json(checks, Checks).checks[0].passed is True
    checks.write_text('{"checks":[{"id":"completion","passed":true,"extra":"secret"}]}')
    with pytest.raises(ContractError, match=r"checks.json.*checks.0.extra") as error:
        load_json(checks, Checks)
    assert "secret" not in str(error.value)
    trigger.write_text('skill="x"\nshould=["y"]\nshould_not=["n"]\nwindow="6"\n')
    with pytest.raises(ContractError, match="window"):
        load_toml(trigger, Trigger)


def test_arms_user_and_nested_guidance() -> None:
    seed = {"src/AGENTS.md": b"nested", "src/CLAUDE.md": b"nested", ".omp/WATCHDOG.md": b"watch",
            "HOME/.omp/agent/skills/x/SKILL.md": b"x", "HOME/.omp/agent/RULES.md": b"skill://x\nkeep\n"}
    assert materialize(seed, "minus:all") == {k: v for k, v in seed.items() if k.startswith("HOME/")}
    assert materialize(seed, "minus:user-all") == {k: v for k, v in seed.items() if not k.startswith("HOME/")}
    user = materialize(seed, "minus:user-skill:x")
    assert user["HOME/.omp/agent/RULES.md"] == b"keep\n"
    assert materialize({"AGENTS.md": "rule://sqlé\nrule://sql\n".encode()}, "minus:rule:sql")["AGENTS.md"] == "rule://sqlé\n".encode()


def test_missing_trials_are_infra_observations(tmp_path: Path) -> None:
    spec = TrialSpec(identity=IdentityInputs(snapshot="s", arm="a", case="c", agent="g", engine="e", replicate=0),
                     arm="current", case_key="f/c", family="f", targets=["all"])
    observations = Store(tmp_path).observations(specs=[spec])
    assert len(observations) == 1
    assert observations[0].infra_error


def test_rubric_versions_require_selection(tmp_path: Path) -> None:
    db = Store(tmp_path)
    spec = TrialSpec(identity=IdentityInputs(snapshot="s", arm="a", case="c", agent="g", engine="e", replicate=0),
                     arm="current", case_key="f/c", family="f", targets=["all"])
    db.save_trial(spec, TrialResult(status="complete"))
    db.save_grade(spec.id, "v1", "j", GradeResult(checks=[GradedCheck(id="completion", passed=True)]))
    db.save_grade(spec.id, "v2", "j", GradeResult(checks=[GradedCheck(id="completion", passed=False)]))
    with pytest.raises(ValueError, match="multiple grades"):
        db.observations()
    assert success(db.observations(verifier_hash="v2")[0].checks) is False


def test_missing_checks_are_unknown_in_diagnostics() -> None:
    observations = [Observation(trial_id="one", arm="current", case_key="f/c", family="f", replicate=0,
                    checks=[GradedCheck(id="completion", passed=True), GradedCheck(id="style", passed=True, critical=False)]),
                    Observation(trial_id="two", arm="current", case_key="f/c", family="f", replicate=1,
                    checks=[GradedCheck(id="completion", passed=True)])]
    result = analyze(observations, "current", "none")
    assert result.check_rates["style"]["current"].low == 0.5
    assert result.check_rates["style"]["current"].high == 1.0


def test_noncritical_unknown_and_protection_scope() -> None:
    obs = Observation(trial_id="one", arm="current", case_key="f/c", family="f", replicate=0,
        checks=[GradedCheck(id="completion", passed=True), GradedCheck(id="style", passed=None, critical=False, source="judge")])
    result = analyze([obs], "current", "none", target="user-rule:x", protected=["all"])
    assert result.unknowns == 1
    assert result.action == "next-look"


def test_numerical_edges() -> None:
    assert regularized_beta(0.5, 1.0, 1.0) == 0.5
    assert abs(t_quantile(0.75, 1) - 1) < 1e-10
    assert t_quantile(0.5, 1) == 0.0
    with pytest.raises(ValueError):
        t_quantile(1.0, 1)


def test_cli_selftest_analyze_and_resume(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["selftest", "--store", str(tmp_path)]) == 0
    manifests = list((tmp_path / "trials").glob("*/manifest.json"))
    timestamps = {p: p.stat().st_mtime_ns for p in manifests}
    assert len(manifests) == 60
    assert main(["selftest", "--store", str(tmp_path)]) == 0
    assert timestamps == {p: p.stat().st_mtime_ns for p in manifests}
    assert main(["analyze", "--store", str(tmp_path)]) == 0
    report = tmp_path / "reports/selftest/report.md"
    assert "| keep | keep |" in report.read_text()
    assert (report.parent / "report.json").is_file()
    assert '"verdict": "keep"' in capsys.readouterr().out
    assert "Per-check separation" in markdown(analyze([], "current", "none"))
