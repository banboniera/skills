from collections import Counter
from pathlib import Path

import pytest

from guidance_evals.cli import FrozenPlan, analyze_plan, plan_path
from guidance_evals.commands import run_experiment
from guidance_evals.contracts import Agent, ContractError, Image, Project, discover_cases, load_json
from guidance_evals.dispatcher import Dispatcher
from guidance_evals.identity import IdentityInputs, admission_id, agent_hash, content_hash, directory_hash, grade_id
from guidance_evals.runtime import FREE_MODEL, RealRunner
from guidance_evals.runner import GradeManifest, GradeResult, GradedCheck, TrialManifest, TrialResult, TrialSpec
from guidance_evals.sandbox import Sandbox, SeedInfo
from guidance_evals.store import Store, atomic_model, atomic_write


class CountingRunner(RealRunner):
    trial_calls = 0
    grade_calls = 0

    def run_trial(self, trial: TrialSpec, *, readonly: bool = False) -> TrialResult:
        self.trial_calls += 1
        return TrialResult(status="complete")

    def grade(self, trial: TrialManifest) -> GradeResult:
        self.grade_calls += 1
        return GradeResult(checks=[GradedCheck(id="completion", passed=True)])


def test_run_regrades_changed_question_without_agent_trials(tmp_path: Path) -> None:
    root = tmp_path / "project"
    case_dir = root / ".omp/evals/cases/family/example"
    (case_dir / "verifier").mkdir(parents=True)
    (case_dir / "case.toml").write_text('id="example"\nprompt="Fix the calculation"\ntargets=["all"]\n')
    (case_dir / "reference.patch").write_text("reference")
    (case_dir / "verifier/verify.sh").write_text("true")
    question = case_dir / "judge.toml"
    question.write_text('[[question]]\nid="style"\ntext="Is the result clear?"\nevidence=["diff"]\n')
    experiment = tmp_path / "experiment.toml"
    experiment.write_text('name="regrade"\nreplicates=1\nlooks=[1]\n')
    project = Project(slug="test", image=Image(containerfile="Containerfile"),
                      agent=Agent(roles={"default": FREE_MODEL}))
    store = Store(tmp_path / "store")
    seed = SeedInfo("image", tmp_path / "seed", "snapshot")
    runner = CountingRunner(root, project, store, Dispatcher(tmp_path / "dispatcher"),
                            Sandbox(root, project, store.root, "run"), seed, {})
    case = discover_cases(root, project)[0]
    admission = admission_id(case.case_hash, directory_hash(case_dir / "verifier"),
        content_hash((case_dir / "reference.patch").read_bytes().hex()), agent_hash(project, seed.image, runner.roles))
    import json
    atomic_write(store.root / "admissions" / admission / "admission.json", json.dumps({
        "admitted": True, "snapshot": seed.snapshot_hash, "image": seed.image}).encode())
    run_experiment(runner, experiment, 2)
    assert runner.trial_calls == 1  # Identical materialized arms share a trial.
    original_trials = {p: p.stat().st_mtime_ns for p in (store.root / "trials").glob("*/manifest.json")}
    old_grades = len(list((store.root / "grades").glob("*/manifest.json")))
    question.write_text(question.read_text().replace("clear?", "clear and concise?"))
    run_experiment(runner, experiment, 2)
    assert runner.trial_calls == 1
    assert runner.grade_calls == 2
    assert len(list((store.root / "grades").glob("*/manifest.json"))) == old_grades + 1
    assert original_trials == {p: p.stat().st_mtime_ns for p in original_trials}
    frozen = load_json(plan_path(store, "regrade"), FrozenPlan)
    assert analyze_plan(store, frozen).infra_errors == 0
    from contextlib import nullcontext
    from unittest.mock import patch
    from guidance_evals.cli import main
    (root / ".omp/evals/project.toml").write_text(
        'slug="test"\n[image]\ncontainerfile="Containerfile"\n[agent.roles]\n'
        f'default="{FREE_MODEL}"\n')
    question.write_text(question.read_text().replace("concise?", "concise and specific?"))
    with patch("guidance_evals.commands.prepared", return_value=nullcontext(runner)):
        assert main(["analyze", "--project", str(root), "--store", str(store.root), "--experiment", "regrade"]) == 0
    assert runner.trial_calls == 1
    assert runner.grade_calls == 3
    assert original_trials == {p: p.stat().st_mtime_ns for p in original_trials}


def test_offline_analysis_preserves_unique_saved_grades_across_engine_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from guidance_evals.plan import Experiment
    import guidance_evals.store as storage
    db = Store(tmp_path)
    spec = TrialSpec(identity=IdentityInputs(snapshot="s", arm="a", case="c", agent="g", engine="e", replicate=0),
                     arm="current", case_key="f/c", family="f", targets=["rule:positive"])
    db.save_trial(spec, TrialResult(status="complete"))
    monkeypatch.setattr(storage, "grading_engine_hash", lambda: "old-engine")
    monkeypatch.setattr("guidance_evals.identity.grading_engine_hash", lambda: "old-engine")
    db.save_grade(spec.id, "v", "j", GradeResult(checks=[GradedCheck(id="completion", passed=True)]))
    monkeypatch.setattr(storage, "grading_engine_hash", lambda: "new-engine")
    monkeypatch.setattr("guidance_evals.identity.grading_engine_hash", lambda: "new-engine")
    frozen = FrozenPlan(experiment=Experiment(name="offline"), trials=[spec],
                        grading_verifiers={spec.id: "v"}, grading_judges={spec.id: "j"})
    assert analyze_plan(db, frozen).infra_errors == 0
    assert db.observations(specs=[spec], engine_hash="old-engine")[0].checks[0].passed is True
    assert db.observations(specs=[spec], engine_hash="new-engine")[0].infra_error is True


def test_multiple_saved_grade_engines_require_explicit_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import guidance_evals.store as storage
    from guidance_evals.plan import Experiment
    db = Store(tmp_path)
    spec = TrialSpec(identity=IdentityInputs(snapshot="s", arm="a", case="c", agent="g", engine="e", replicate=0),
                     arm="current", case_key="f/c", family="f", targets=["all"])
    db.save_trial(spec, TrialResult(status="complete"))
    for engine, passed in [("old-engine", False), ("new-engine", True)]:
        monkeypatch.setattr(storage, "grading_engine_hash", lambda: engine)
        monkeypatch.setattr("guidance_evals.identity.grading_engine_hash", lambda: engine)
        db.save_grade(spec.id, "v", "j", GradeResult(checks=[GradedCheck(id="completion", passed=passed)]))
    with pytest.raises(ValueError, match="multiple grades"):
        db.observations(specs=[spec], verifier_hash="v", judge_hash="j")
    assert db.observations(specs=[spec], engine_hash="old-engine")[0].checks[0].passed is False
    frozen = FrozenPlan(experiment=Experiment(name="pinned"), trials=[spec],
                        grading_engines={spec.id: "old-engine"})
    assert analyze_plan(db, frozen).check_rates["completion"]["current"].low == 0
    assert analyze_plan(db, frozen, engine_hash="new-engine").check_rates["completion"]["current"].low == 1


@pytest.fixture
def versioned_store(tmp_path: Path) -> tuple[Store, list[TrialSpec]]:
    db = Store(tmp_path)
    specs: list[TrialSpec] = []
    for case in ["first", "second", "unrelated"]:
        spec = TrialSpec(identity=IdentityInputs(snapshot="s", arm="a", case=case, agent="g", engine="e", replicate=0),
                         arm="current", case_key=f"f/{case}", family="f", targets=["all"])
        specs.append(spec)
        db.save_trial(spec, TrialResult(status="complete", cost=0.25, tokens=10, seconds=2))
        for verifier, judge, engine, passed in [
            ("v-old", "j-old", "old-engine", False),
            ("v-new", "j-new", "new-engine", True),
            ("v-new", "j-old", "old-engine", True),
            ("v-old", "j-new", "old-engine", True),
            ("v-old", "j-old", "new-engine", True),
        ]:
            ident = grade_id(spec.id, verifier, judge, engine)
            atomic_model(db.root / "grades" / ident / "manifest.json",
                GradeManifest(trial_id=spec.id, verifier_hash=verifier, judge_hash=judge, engine_hash=engine,
                    result=GradeResult(checks=[GradedCheck(id="completion", passed=passed)],
                                       confirmed_critical_counterexample=passed)))
    return db, specs


def test_observations_batch_selects_mixed_versions_and_parses_each_manifest_once(
    versioned_store: tuple[Store, list[TrialSpec]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    import guidance_evals.store as storage
    db, specs = versioned_store
    first, second = specs[:2]
    loaded: Counter[Path] = Counter()
    original = storage.load_json

    def counted_load(path: Path, model: type[GradeManifest] | type[TrialManifest]) -> GradeManifest | TrialManifest:
        loaded[path] += 1
        return original(path, model)

    monkeypatch.setattr(storage, "load_json", counted_load)
    observations = db.observations(specs=[second, first], grading_versions={
        first.id: ("v-old", "j-old", "old-engine"),
        second.id: ("v-new", "j-new", "new-engine"),
    })
    assert [item.trial_id for item in observations] == [second.id, first.id]
    assert [item.checks[0].passed for item in observations] == [True, False]
    assert [item.confirmed_critical_counterexample for item in observations] == [True, False]
    assert all(not item.infra_error for item in observations)
    assert [(item.cost, item.tokens, item.seconds) for item in observations] == [(0.25, 10, 2), (0.25, 10, 2)]
    grade_paths = set((db.root / "grades").glob("*/manifest.json"))
    assert {path: count for path, count in loaded.items() if path.parent.parent.name == "grades"} == {
        path: 1 for path in grade_paths
    }
    assert loaded[db.trial_path(first.id) / "manifest.json"] == 1
    assert loaded[db.trial_path(second.id) / "manifest.json"] == 1


def test_observations_batch_uses_uniform_filters_for_unmapped_trials(
    versioned_store: tuple[Store, list[TrialSpec]],
) -> None:
    db, specs = versioned_store
    first, second = specs[:2]
    observations = db.observations(specs=[first, second],
        verifier_hash="v-new", judge_hash="j-new", engine_hash="new-engine",
        grading_versions={first.id: ("v-old", "j-old", "old-engine")})
    assert [item.checks[0].passed for item in observations] == [False, True]
    assert all(not item.infra_error for item in observations)
    uniform = db.observations(specs=[first, second],
        verifier_hash="v-old", judge_hash="j-old", engine_hash="old-engine")
    assert [item.checks[0].passed for item in uniform] == [False, False]


def test_observations_batch_refuses_ambiguous_versions(
    versioned_store: tuple[Store, list[TrialSpec]],
) -> None:
    db, specs = versioned_store
    first, second = specs[:2]
    with pytest.raises(ValueError, match="multiple grades"):
        db.observations(specs=[first, second], grading_versions={
            first.id: ("v-old", "j-old", None),
            second.id: ("v-new", "j-new", "new-engine"),
        })
    with pytest.raises(ValueError, match="multiple grades"):
        db.observations(specs=[first], verifier_hash="v-old", judge_hash="j-old", engine_hash="old-engine",
                        grading_versions={first.id: (None, None, None)})


def test_observations_batch_validates_unrelated_grade_identity(
    versioned_store: tuple[Store, list[TrialSpec]],
) -> None:
    db, specs = versioned_store
    first, second, unrelated = specs
    # Valid JSON/model, but the manifest is committed under another grade's identity.
    atomic_model(db.root / "grades" / ("0" * 64) / "manifest.json",
        GradeManifest(trial_id=unrelated.id, verifier_hash="other", judge_hash="other", engine_hash="other",
                      result=GradeResult()))
    with pytest.raises(ContractError, match="identity: grade mismatch"):
        db.observations(specs=[first, second], grading_versions={
            first.id: ("v-old", "j-old", "old-engine"),
            second.id: ("v-new", "j-new", "new-engine"),
        })
