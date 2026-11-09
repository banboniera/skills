from pathlib import Path

import pytest

from guidance_evals.analysis import analyze
from guidance_evals.contracts import Case
from guidance_evals.identity import IdentityInputs, case_execution_hash, directory_hash, grade_id, tree_hash
from guidance_evals.runner import GradedCheck, Observation


def observation(case: str, arm: str, replicate: int, passed: bool, cost: float) -> Observation:
    return Observation(trial_id=f"{case}-{arm}-{replicate}", case_key=case, family=case, arm=arm,
        replicate=replicate, checks=[GradedCheck(id="completion", passed=passed)],
        cost=cost, tokens=int(cost * 100), seconds=cost * 10, exposed=True)


def test_equal_case_weights_and_unbalanced_look() -> None:
    records = [observation("first", "with", i, True, 2) for i in range(3)]
    records += [observation("first", "without", i, False, 1) for i in range(3)]
    records += [observation("second", "with", i, False, 1) for i in range(6)]
    records += [observation("second", "without", i, False, 1) for i in range(6)]
    result = analyze(records, "with", "without")
    assert result.effect.low == 0.5
    assert result.cost_delta == 0.5
    assert result.tokens_delta == 50
    assert result.seconds_delta == 5
    assert result.verdict == "inconclusive"
    assert any("balanced fixed look" in warning for warning in result.warnings)


def test_unknown_baseline_widens_upper_and_lower_effects() -> None:
    records = [observation(f"case-{case}", arm, i, True, 1) for case in range(10)
               for arm in ["with", "without"] for i in range(3)]
    known = analyze(records, "with", "without")
    records[-1].checks.append(GradedCheck(id="unknown", passed=None, source="judge"))
    uncertain = analyze(records, "with", "without")
    assert uncertain.effect.high > known.effect.high
    assert uncertain.bound.high > known.bound.high
    assert uncertain.t is None


def test_verdict_robust_to_unknown_noncritical_judgment_keeps_its_action() -> None:
    # Six families, k=3: guidance breaks every with-arm trial (harm); one judged
    # question stays unknown. The bound already spans its worst and best value.
    records = [observation(f"case-{case}", arm, i, arm == "without", 1) for case in range(6)
               for arm in ["with", "without"] for i in range(3)]
    records[0].checks.append(GradedCheck(id="judged", passed=None, critical=False, source="judge"))
    result = analyze(records, "with", "without")
    assert result.verdict == "harm"
    assert result.action == "fix-or-delete"


def test_judge_quality_counts_unknowns_and_disagreements() -> None:
    records = [observation(f"case-{case}", arm, i, True, 1) for case in range(2)
               for arm in ["with", "without"] for i in range(2)]
    for index, record in enumerate(records):
        record.checks.append(GradedCheck(id="q", passed=None if index == 0 else True, critical=False,
                                         source="judge", disagreement=index < 3))
    quality = analyze(records, "with", "without").judge_quality["q"]
    assert (quality.trials, quality.unknown, quality.disagreements, quality.compared) == (8, 1, 3, 8)


def test_grading_changes_preserve_trial_identity(tmp_path: Path) -> None:
    case = Case(id="case", targets=["all"], prompt="work")
    verifier = tmp_path / "verifier/verify.sh"
    verifier.parent.mkdir()
    verifier.write_bytes(b"echo 1")
    judge = tmp_path / "judge.toml"
    judge.write_text("question=[]")
    before = IdentityInputs(snapshot="s", arm=tree_hash({"AGENTS.md": b"a"}),
        case=case_execution_hash(case, tmp_path), agent="g", engine="e", replicate=0)
    old_grade = grade_id(before.trial_id, directory_hash(verifier.parent), directory_hash(tmp_path))
    verifier.write_bytes(b"echo 2")
    judge.write_text('question=[{id="new"}]')
    after = before.model_copy(update={"case": case_execution_hash(case, tmp_path), "engine": "new-engine"})
    assert before.trial_id == after.trial_id
    assert old_grade != grade_id(after.trial_id, directory_hash(verifier.parent), directory_hash(tmp_path))
    changed = case.model_copy(update={"prompt": "different work"})
    assert before.trial_id != before.model_copy(update={"case": case_execution_hash(changed, tmp_path)}).trial_id


def test_confirmed_counterexample_is_harm_even_with_sparse_cases() -> None:
    record = observation("one", "with", 0, False, 1)
    record.confirmed_critical_counterexample = True
    result = analyze([record], "with", "without")
    assert result.verdict == "harm"
    assert result.action == "fix-or-delete"


def test_block_protection_includes_user_all() -> None:
    result = analyze([], "with", "without", target="mixed", members=["user-rule:security"], protected=["user-all"])
    assert result.action == "next-look"


def test_incomplete_panels_cannot_authorize_deletion() -> None:
    assert analyze([], "with", "without").action == "next-look"
    infra = observation("one", "with", 0, True, 0)
    infra.infra_error = True
    assert analyze([infra], "with", "without").action == "retry"
    partial = [observation(f"case-{case}", arm, i, True, 0) for case in range(6)
               for arm in ["with", "without"] for i in range(2)]
    assert analyze(partial, "with", "without").action == "next-look"
    sparse = [observation("one", arm, i, True, 0) for arm in ["with", "without"] for i in range(6)]
    assert analyze(sparse, "with", "without").action == "add-cases"
    complete = [observation(f"case-{case}", arm, i, True, 0) for case in range(6)
                for arm in ["with", "without"] for i in range(6)]
    for record in complete:
        record.exposed = False
    assert analyze(complete, "with", "without").action == "fix-trigger"


def panel(cases: int, replicates: int, with_pass: bool = True,
          without_pass: bool = True) -> list[Observation]:
    return [observation(f"case-{case}", arm, rep, passed, 0)
            for case in range(cases)
            for arm, passed in [("with", with_pass), ("without", without_pass)]
            for rep in range(replicates)]


def test_resolved_first_look_keeps_guidance() -> None:
    result = analyze(panel(6, 3, True, False), "with", "without")
    assert abs(result.bound.low - 0.507) <= 0.001
    assert result.bound.high == 1.0
    assert result.verdict == "keep"
    assert result.action == "keep"


def test_resolved_first_look_benefit_keeps_guidance() -> None:
    records = panel(6, 3, True, False)
    for record in records:
        if record.arm == "with" and record.case_key in {"case-0", "case-1", "case-2"}:
            record.checks[0].passed = False
    result = analyze(records, "with", "without")
    assert 0 < result.bound.low < 0.1
    assert result.verdict == "benefit"
    assert result.action == "keep"


def test_resolved_first_look_harm_stops_without_another_look() -> None:
    result = analyze(panel(6, 3, False, True), "with", "without")
    assert result.verdict == "harm"
    assert result.action == "fix-or-delete"


def test_resolved_first_look_equivalence_deletes_complete_panel() -> None:
    result = analyze(panel(160, 3), "with", "without")
    assert result.verdict == "equivalent"
    assert result.action == "delete"


@pytest.mark.parametrize(("exposed", "action", "zero_warnings"), [
    (True, "keep", 0), (False, "fix-trigger", 1), (None, "keep", 0),
])
def test_only_known_with_arm_zero_exposure_warns(
    exposed: bool | None, action: str, zero_warnings: int,
) -> None:
    records = panel(6, 3, True, False)
    for record in records:
        record.exposed = exposed if record.arm == "with" else False
    result = analyze(records, "with", "without")
    assert result.action == action
    warnings = [warning for warning in result.warnings if "Target never loaded" in warning]
    assert len(warnings) == zero_warnings
    assert all("(with: 0/" in warning for warning in warnings)


@pytest.mark.parametrize(("replicates", "final_look", "target", "protected", "costs_context", "action"), [
    (3, 6, "rule:x", (), True, "next-look"),
    (6, 6, "rule:x", (), True, "delete-if-costs-context"),
    (6, 6, "rule:x", ("rule:x",), True, "keep"),
    (6, 6, "rule:x", (), False, "keep"),
    (3, 3, "rule:x", (), True, "delete-if-costs-context"),
    (2, 3, "rule:x", (), True, "next-look"),
    # An inconclusive whole-harness screen never deletes the harness.
    (6, 6, "all", (), True, "keep"),
    (6, 6, "user-all", (), True, "keep"),
])
def test_unresolved_look_uses_final_policy_only_when_complete(
    replicates: int, final_look: int, target: str, protected: tuple[str, ...],
    costs_context: bool, action: str,
) -> None:
    result = analyze(panel(6, replicates), "with", "without", target=target, final_look=final_look,
                     protected=protected, costs_context=costs_context)
    assert result.verdict == "inconclusive"
    assert result.action == action


@pytest.mark.parametrize("defect", ["empty", "infra", "partial", "unpaired", "few-families",
                                   "repeated-family", "ungraded", "zero-exposure", "unknown-exposure"])
def test_unsafe_panels_never_authorize_deletion(defect: str) -> None:
    records = panel(160, 3)
    if defect == "empty":
        records = []
    elif defect == "infra":
        records[0].infra_error = True
    elif defect == "partial":
        records.pop()
    elif defect == "unpaired":
        records = [record for record in records
                   if not (record.case_key == "case-0" and record.arm == "without")]
    elif defect == "few-families":
        records = panel(5, 3)
    elif defect == "repeated-family":
        for record in records:
            record.family = "shared"
    elif defect == "ungraded":
        records[0].checks = []
    else:
        for record in records:
            if record.arm == "with":
                record.exposed = None if defect == "unknown-exposure" else False
    result = analyze(records, "with", "without", final_look=3)
    assert result.action not in {"delete", "delete-if-costs-context", "fix-or-delete"}
