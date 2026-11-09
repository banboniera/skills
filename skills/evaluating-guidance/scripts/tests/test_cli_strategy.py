import json
from pathlib import Path

import pytest

from guidance_evals.cli import FrozenPlan, main
from guidance_evals.contracts import load_json
from guidance_evals.plan import is_holdout
from guidance_evals.runner import GradeResult, GradedCheck, TrialResult
from guidance_evals.store import Store


def test_cli_expands_block_strategy_and_advances_only_unresolved_comparisons(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "project"
    evals = root / ".omp/evals"
    evals.mkdir(parents=True)
    (evals / "project.toml").write_text('slug="demo"\nimage={containerfile="Containerfile"}\n[agent]\nroles={default="model"}\n[blocks]\ndata=["rule:sql","rule:database"]\n')
    family = next(f"f{i}" for i in range(100) if not is_holdout(f"f{i}", 30))
    case = evals / "cases" / family / "task"
    case.mkdir(parents=True)
    (case / "case.toml").write_text('id="task"\nprompt="do work"\ntargets=["rule:sql"]\n')
    experiment = tmp_path / "experiment.toml"
    experiment.write_text('name="campaign"\nkind="blocks"\n')
    identities = tmp_path / "identity.json"
    identities.write_text(json.dumps({"snapshot": "s", "arm_hashes": {"current": "a", "minus:data": "b"}, "agent_hash": "g", "engine_hash": "e"}))
    db = Store(tmp_path / "store")
    argv = ["plan", "--project", str(root), "--experiment", str(experiment), "--identity", str(identities), "--store", str(db.root)]
    assert main(argv) == 0
    frozen = load_json(db.root / "experiments/campaign--data/plan.json", FrozenPlan)
    assert len(frozen.trials) == 6
    for spec in frozen.trials:
        db.save_trial(spec, TrialResult(status="complete"))
        db.save_grade(spec.id, "v", "j", GradeResult(checks=[GradedCheck(id="completion", passed=True)]))
    assert main([*argv, "--next-look"]) == 0
    second = load_json(db.root / "experiments/campaign--data/plan.json", FrozenPlan)
    assert len(second.trials) == 12
    assert second.experiment.replicates == 6
    assert {spec.id for spec in frozen.trials} <= {spec.id for spec in second.trials}
    assert main(["analyze", "--store", str(db.root), "--experiment", "campaign--data"]) == 0
    data = json.loads((db.root / "reports/campaign--data/report.json").read_text())
    assert data["target"] == "data"
    assert set(data["member_separation"]) == {"rule:sql", "rule:database"}
    assert "comparisons" in capsys.readouterr().out


def test_free_model_experiments_never_authorize_guidance_changes(tmp_path: Path) -> None:
    from guidance_evals.cli import analyze_plan, selftest
    db = Store(tmp_path)
    frozen = selftest(db)
    frozen = frozen.model_copy(update={"smoke_only": True})
    result = analyze_plan(db, frozen)
    assert result.verdict == "inconclusive"
    assert result.action == "smoke only; do not change project guidance"
    assert any("free/local" in warning for warning in result.warnings)


def test_store_status_does_not_require_the_original_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["status", "--store", str(tmp_path / "store")]) == 0
    assert json.loads(capsys.readouterr().out)["complete"] == 0


def test_explicit_status_project_requires_configuration(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status", "--project", str(tmp_path), "--store", str(tmp_path / "store")]) == 2
    assert "cannot read valid TOML" in capsys.readouterr().err


def test_holdout_percent_is_frozen_even_when_selected_cases_do_not_change(tmp_path: Path) -> None:
    root = tmp_path / "project"
    evals = root / ".omp/evals"
    evals.mkdir(parents=True)
    project_file = evals / "project.toml"
    project_text = 'slug="demo"\nholdout=0\nimage={containerfile="Containerfile"}\n[agent]\nroles={default="model"}\n'
    project_file.write_text(project_text)
    family = next(f"family-{i}" for i in range(100) if not is_holdout(f"family-{i}", 30))
    case = evals / "cases" / family / "task"
    case.mkdir(parents=True)
    (case / "case.toml").write_text('id="task"\nprompt="work"\ntargets=["all"]\n')
    experiment = tmp_path / "experiment.toml"
    experiment.write_text('name="frozen"\n')
    identities = tmp_path / "identity.json"
    identities.write_text(json.dumps({"snapshot": "s", "arm_hashes": {"current": "a", "none": "b"}, "agent_hash": "g"}))
    store = tmp_path / "store"
    argv = ["plan", "--project", str(root), "--experiment", str(experiment),
            "--identity", str(identities), "--store", str(store)]
    assert main(argv) == 0
    path = store / "experiments/frozen/plan.json"
    original = load_json(path, FrozenPlan)
    assert original.experiment.holdout == 0
    assert main(argv) == 0
    project_file.write_text(project_text.replace("holdout=0", "holdout=30"))
    assert main(argv) == 2
    assert load_json(path, FrozenPlan) == original


def test_comparison_relevance_and_override_resolve_the_same_members(tmp_path: Path) -> None:
    from guidance_evals.cli import analyze_plan
    from guidance_evals.plan import Experiment
    db = Store(tmp_path)
    frozen = FrozenPlan(experiment=Experiment(name="positive",
        arms=["minus:rule:negative", "minus:monetary"], relevant_targets=["rule:positive"]),
        trials=[], blocks={"monetary": ["rule:positive", "rule:negative"]})
    result = analyze_plan(db, frozen)
    assert result.target == "rule:positive"
    assert set(result.member_separation) == {"rule:positive"}
    overridden = analyze_plan(db, frozen, target="monetary")
    assert overridden.target == "monetary"
    assert set(overridden.member_separation) == {"rule:positive", "rule:negative"}
    multiple = frozen.model_copy(update={"experiment": frozen.experiment.model_copy(
        update={"relevant_targets": ["rule:positive", "file:AGENTS.md"]})})
    result = analyze_plan(db, multiple)
    assert result.target == "targets: rule:positive, file:AGENTS.md"
    assert set(result.member_separation) == {"rule:positive", "file:AGENTS.md"}


def test_resolved_relevance_members_control_protection(tmp_path: Path) -> None:
    from guidance_evals.cli import analyze_plan, selftest
    from guidance_evals.identity import content_hash
    db = Store(tmp_path)
    frozen = selftest(db)
    for spec in frozen.trials:
        db.save_grade(spec.id, content_hash("fake-verifier-v1"), content_hash("no-judge"),
                      GradeResult(checks=[GradedCheck(id="completion", passed=True)]))
    frozen.experiment.looks = [3]
    frozen.experiment.relevant_targets = ["file:AGENTS.md", "rule:positive"]
    frozen.protected = ["rule:positive"]
    assert analyze_plan(db, frozen).action == "keep"
    assert analyze_plan(db, frozen, target="file:AGENTS.md").action == "delete-if-costs-context"


def test_legacy_shared_ablations_do_not_mislabel_the_contrast(tmp_path: Path) -> None:
    from guidance_evals.cli import analyze_plan
    from guidance_evals.plan import Experiment
    frozen = FrozenPlan(experiment=Experiment(name="positive",
        arms=["minus:rule:negative", "minus:monetary"],
        relevant_targets=["rule:positive", "rule:negative"]),
        trials=[], blocks={"monetary": ["rule:positive", "rule:negative"]})
    result = analyze_plan(Store(tmp_path), frozen)
    assert result.target == "rule:positive"
    assert set(result.member_separation) == {"rule:positive"}
