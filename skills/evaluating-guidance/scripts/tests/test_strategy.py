from pathlib import Path

from guidance_evals import analysis, arms, contracts, plan, runner


def test_blocks_remove_members_and_rows() -> None:
    blocks = {"data": ["rule:database", "rule:sql"]}
    seed = {"AGENTS.md": b"rule://database\nrule://sql\nrule://other\n", ".omp/rules/database.md": b"d", ".omp/rules/sql.md": b"s"}
    assert arms.materialize(seed, "minus:data", blocks=blocks) == {"AGENTS.md": b"rule://other\n"}
    project = contracts.Project(slug="demo", image=contracts.Image(containerfile="Containerfile"),
                                agent=contracts.Agent(roles={"default": "model"}), blocks=blocks)
    assert project.blocks == blocks


def test_layered_strategies_and_block_relevance(tmp_path: Path) -> None:
    blocks = {"data": ["rule:sql", "rule:database"], "style": ["rule:style"]}
    expanded = plan.expand_experiments(plan.Experiment(name="campaign", kind="blocks"), blocks)
    assert len(expanded.comparisons) == 2
    comparison = expanded.comparisons[0]
    assert comparison.arms == ["current", "minus:data"]
    family = next(f"f{i}" for i in range(100) if not plan.is_holdout(f"f{i}", 30))
    cases = [contracts.DiscoveredCase(spec=contracts.Case(id="sql", prompt="work", targets=["rule:sql"]), family=family, path=tmp_path, case_hash="sql"),
             contracts.DiscoveredCase(spec=contracts.Case(id="style", prompt="work", targets=["rule:style"]), family=family, path=tmp_path, case_hash="style")]
    assert [c.spec.id for c in plan.select_cases(comparison, cases)] == ["sql"]
    split = plan.expand_experiments(plan.Experiment(name="sub", kind="split", block="data"), blocks)
    assert len(split.comparisons) == 2
    assert {tuple(e.relevant_targets) for e in split.comparisons} == {("rule:sql",), ("rule:database",)}
    whole = plan.expand_experiments(plan.Experiment(name="whole", kind="whole"), blocks)
    assert whole.comparisons[0].arms == ["current", "none"]
    holdout = plan.expand_experiments(plan.Experiment(name="holdout", kind="holdout", ref="abc"), blocks)
    assert holdout.comparisons[0].arms == ["current", "ref:abc"]
    assert holdout.comparisons[0].split == "holdout"


def test_next_look_advances_entire_unresolved_comparison() -> None:
    exp = plan.Experiment(name="test", kind="compare")
    next_exp = plan.advance_look(exp, "inconclusive")
    assert next_exp is not None and next_exp.replicates == 6
    assert plan.advance_look(exp, "keep") is None
    assert plan.advance_look(next_exp, "inconclusive") is None


def test_cancelling_block_members_force_split() -> None:
    observations: list[runner.Observation] = []
    for case in range(6):
        for arm in ["current", "minus:block"]:
            for rep in range(3):
                observations.append(runner.Observation(trial_id=f"{case}-{arm}-{rep}", arm=arm,
                    case_key=f"f{case}/c", family=f"f{case}", replicate=rep,
                    targets=["rule:helpful", "rule:harmful"], checks=[
                        runner.GradedCheck(id="completion", passed=True),
                        runner.GradedCheck(id="helpful", passed=arm == "current", targets=["rule:helpful"]),
                        runner.GradedCheck(id="harmful", passed=arm != "current", targets=["rule:harmful"])]))
    result = analysis.analyze(observations, "current", "minus:block", target="block",
                              members=["rule:helpful", "rule:harmful"])
    assert result.effect.low == 0.0
    assert result.verdict == "split"
    assert result.action == "split"
    assert result.member_separation["rule:helpful"].effect.low == 0.5
    assert result.member_separation["rule:harmful"].effect.high == -0.5


def test_check_targets_default_to_case_targets() -> None:
    observations = [runner.Observation(trial_id=arm, arm=arm, case_key="f/c", family="f", replicate=0,
                    targets=["rule:x"], checks=[runner.GradedCheck(id="completion", passed=True),
                    runner.GradedCheck(id="detail", passed=arm == "current")]) for arm in ["current", "minus:b"]]
    result = analysis.analyze(observations, "current", "minus:b", members=["rule:x"])
    assert result.member_separation["rule:x"].effect.low == 0.5


def test_explicit_relevance_does_not_expand_to_other_ablation_members() -> None:
    strategy = plan.Experiment(name="positive", arms=["minus:rule:negative", "minus:monetary"],
                               relevant_targets=["rule:positive"])
    comparison = plan.expand_experiments(strategy, {"monetary": ["rule:positive", "rule:negative"]}).comparisons[0]
    assert comparison.relevant_targets == ["rule:positive"]


def test_inferred_relevance_excludes_targets_removed_from_both_arms(tmp_path: Path) -> None:
    strategy = plan.Experiment(name="positive", arms=["minus:rule:negative", "minus:monetary"], holdout=0)
    comparison = plan.expand_experiments(strategy, {"monetary": ["rule:positive", "rule:negative"]}).comparisons[0]
    cases = [contracts.DiscoveredCase(spec=contracts.Case(id=name, prompt="work", targets=[f"rule:{name}"]),
                                      family=name, path=tmp_path, case_hash=name) for name in ["positive", "negative"]]
    assert [case.spec.id for case in plan.select_cases(comparison, cases)] == ["positive"]
