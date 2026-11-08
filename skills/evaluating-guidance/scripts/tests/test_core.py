from pathlib import Path

import pytest
from pydantic import ValidationError

from guidance_evals import analysis, arms, contracts, identity, plan, runner, store


def project() -> contracts.Project:
    return contracts.Project(slug="demo", image=contracts.Image(containerfile="Containerfile"),
                             agent=contracts.Agent(roles={"default": "model"}))


def test_contracts_report_file_and_field(tmp_path: Path) -> None:
    path = tmp_path / "case.toml"
    path.write_text('id="c"\nprompt="do work"\ntargets=["wat:x"]\n')
    with pytest.raises(contracts.ContractError, match=r"case.toml.*targets"):
        contracts.load_toml(path, contracts.Case)
    with pytest.raises(ValidationError):
        contracts.Checks.model_validate({"checks": [{"id": "a", "passed": "yes"}]})
    with pytest.raises(ValidationError):
        contracts.Project.model_validate({"slug": "demo", "unexpected": True})


def test_discovery_family_services_and_duplicates(tmp_path: Path) -> None:
    root = tmp_path / ".omp/evals/cases"
    case = root / "family/one"
    case.mkdir(parents=True)
    text = 'id="unique"\nprompt="do work"\ntargets=["all"]\n'
    (case / "case.toml").write_text(text)
    found = contracts.discover_cases(tmp_path, project())
    assert found[0].family == "family"
    assert found[0].key == "family/unique"
    (case / "case.toml").write_text(text + 'services=["missing"]\n')
    with pytest.raises(contracts.ContractError, match="services"):
        contracts.discover_cases(tmp_path, project())
    (case / "case.toml").write_text(text)
    second = root / "family/two"
    second.mkdir(parents=True)
    (second / "case.toml").write_text(text)
    with pytest.raises(contracts.ContractError, match="duplicate"):
        contracts.discover_cases(tmp_path, project())


def test_hashes_stable_sensitive_and_modes(tmp_path: Path) -> None:
    assert identity.content_hash({"b": 2, "a": 1}) == identity.content_hash({"a": 1, "b": 2})
    a = {"AGENTS.md": b"one", "x": b"two"}
    assert identity.tree_hash(a) == identity.tree_hash(dict(reversed(list(a.items()))))
    assert identity.tree_hash(a) != identity.tree_hash(a | {"x": b"Two"})
    assert identity.tree_hash(a) != identity.tree_hash(a, {"x": 0o755})
    (tmp_path / "x").write_bytes(b"x")
    before = identity.directory_hash(tmp_path)
    (tmp_path / "x").chmod(0o755)
    assert before != identity.directory_hash(tmp_path)
    inputs = identity.IdentityInputs(snapshot="s", arm="a", case="c", agent="g", engine="e", replicate=0)
    assert inputs.trial_id != inputs.model_copy(update={"case": "C"}).trial_id
    assert identity.grade_id(inputs.trial_id, "v", "j") != identity.grade_id(inputs.trial_id, "V", "j")


def test_arms_remove_exact_index_rows_and_scopes() -> None:
    seed = {"AGENTS.md": b"rule://sql\nrule://sql-more\nskill://release\n", ".omp/rules/sql.md": b"SQL",
            "src/AGENTS.md": b"rule://sql\nkeep\n", "CLAUDE.md": b"hi", "src/code.py": b"code",
            ".omp/skills/release/SKILL.md": b"release", "HOME/.omp/agent/rules/sql.md": b"user",
            "HOME/.omp/agent/AGENTS.md": b"rule://sql\nuser\n"}
    removed = arms.materialize(seed, "minus:rule:sql")
    assert removed["AGENTS.md"] == b"rule://sql-more\nskill://release\n"
    assert removed["src/AGENTS.md"] == b"keep\n"
    assert ".omp/rules/sql.md" not in removed
    assert "src/code.py" not in removed
    assert "HOME/.omp/agent/rules/sql.md" in removed
    assert "CLAUDE.md" not in arms.materialize(seed, "none")
    assert arms.materialize(seed, "none") == {k: v for k, v in arms.materialize(seed, "current").items() if k.startswith("HOME/")}
    assert "HOME/.omp/agent/rules/sql.md" not in arms.materialize(seed, "minus:user-rule:sql")
    assert arms.materialize(seed, "ref:abc", {"AGENTS.md": b"old"}) == {"AGENTS.md": b"old"}
    with pytest.raises(ValueError):
        arms.materialize(seed, "minus:file:../escape")


def trials(count: int, with_pass: bool | None, without_pass: bool | None,
           replicates: int = 3) -> list[runner.Observation]:
    records: list[runner.Observation] = []
    for case in range(count):
        for arm, passed in [("current", with_pass), ("none", without_pass)]:
            for rep in range(replicates):
                records.append(runner.Observation(trial_id=f"{case}-{arm}-{rep}", case_key=f"f{case}/c",
                    family=f"f{case}", arm=arm, replicate=rep,
                    checks=[runner.GradedCheck(id="completion", passed=True),
                            runner.GradedCheck(id="behavior", passed=passed, source="judge")],
                    cost=1.0, tokens=10, seconds=2.0, exposed=arm == "current"))
    return records


@pytest.mark.parametrize(("df", "expected"), [(2, 4.303), (5, 2.571), (30, 2.042)])
def test_t_quantile(df: int, expected: float) -> None:
    assert abs(analysis.t_quantile(0.975, df) - expected) < 0.001
    assert abs(analysis.t_quantile(0.025, df) + expected) < 0.001


def test_analysis_known_effects_and_unknowns() -> None:
    assert analysis.analyze(trials(10, True, False), "current", "none").verdict == "keep"
    assert analysis.analyze(trials(10, False, True), "current", "none").verdict == "harm"
    assert analysis.analyze(trials(160, True, True), "current", "none").verdict == "equivalent"
    small = analysis.analyze(trials(2, True, True), "current", "none", target="rule:sql", protected=["rule:sql"])
    assert small.verdict == "inconclusive"
    assert small.action == "next-look"
    known = analysis.analyze(trials(10, True, False), "current", "none")
    unknown = analysis.analyze(trials(10, None, False), "current", "none")
    assert unknown.bound.low < known.bound.low
    assert unknown.unknowns == 30
    reliability = unknown.pass_k["current"]
    assert reliability is not None
    assert reliability.low == 0.0
    assert reliability.high == 1.0
    assert known.check_rates["behavior"]["none"].low == 0.0
    assert known.exposure["none"].exposed == 0


def test_success_failure_dominates_unknown() -> None:
    checks = [runner.GradedCheck(id="completion", passed=False), runner.GradedCheck(id="j", passed=None)]
    assert analysis.success(checks) is False
    assert analysis.success([runner.GradedCheck(id="j", passed=None)]) is None
    assert analysis.success([]) is None


def test_plan_resume_incomplete_and_infra(tmp_path: Path) -> None:
    db = store.Store(tmp_path)
    case = contracts.DiscoveredCase(spec=contracts.Case(id="c", prompt="work", targets=["all"]),
                                    family="family", path=tmp_path, case_hash="case")
    exp = plan.Experiment(name="test", arms=["current", "none"], replicates=3, split="holdout")
    # Split selection is tested separately; select the actual deterministic split here.
    exp = exp.model_copy(update={"split": "holdout" if plan.is_holdout("family", 30) else "behavior"})
    items = plan.plan_trials(exp, [case], snapshot="s", arm_hashes={"current": "a", "none": "b"},
                             agent_hash="g", engine_hash="e")
    assert len(items) == 6
    assert {x.arm for x in items[:2]} == {"current", "none"}
    first = items[0]
    db.save_trial(first, runner.TrialResult(status="complete"))
    assert [s for s in items if db.needs_trial(s.id)] == items[1:]
    db.trial_path(items[1].id).mkdir(parents=True)
    assert db.needs_trial(items[1].id)
    db.save_trial(items[2], runner.TrialResult(status="infra_error", error="fixture unavailable"))
    assert db.needs_trial(items[2].id)
    assert db.load_trial(items[2].id).result.status == "infra_error"


def test_holdout_is_stable_and_sealed() -> None:
    assert plan.is_holdout("scope", 30) == plan.is_holdout("scope", 30)
    families = [f"family-{i}" for i in range(1000)]
    assert 200 < sum(plan.is_holdout(f, 30) for f in families) < 400
    import hashlib
    assert not any(plan.is_holdout(family, 0) for family in families)
    assert all(plan.is_holdout(family, 30) ==
               (int.from_bytes(hashlib.sha256(family.encode()).digest(), "big") % 100 < 30)
               for family in families)


def test_project_holdout_is_planning_only() -> None:
    config = project()
    assert config.holdout == 30
    controls = config.model_copy(update={"holdout": 0})
    assert identity.agent_hash(config, "image", config.agent.roles) == identity.agent_hash(controls, "image", controls.agent.roles)
    for percent in [-1, 51, 30.5, True]:
        with pytest.raises(ValidationError):
            contracts.Project.model_validate({**config.model_dump(), "holdout": percent})


def test_smoke_model_must_be_free_and_does_not_change_agent_identity() -> None:
    config = project()
    other = config.model_copy(update={"smoke_model": "local/qwen2.5-1.5b"})
    assert identity.agent_hash(config, "image", config.agent.roles) == identity.agent_hash(other, "image", other.agent.roles)
    with pytest.raises(ValidationError):
        contracts.Project.model_validate({**config.model_dump(), "smoke_model": "anthropic/claude-opus-5-5"})


def test_fake_runner_store_and_grading(tmp_path: Path) -> None:
    fake = runner.FakeRunner()
    inputs = identity.IdentityInputs(snapshot="s", arm="a", case="c", agent="g", engine="e", replicate=0)
    trial = runner.TrialSpec(identity=inputs, arm="current", case_key="f/c", family="f", targets=["all"])
    db = store.Store(tmp_path)
    result = fake.run_trial(trial)
    db.save_trial(trial, result)
    grade = fake.grade(db.load_trial(trial.id))
    db.save_grade(trial.id, "v", "j", grade)
    assert len(db.observations()) == 1
    assert db.observations()[0].checks[0].passed is True
