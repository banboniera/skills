from pathlib import Path

from guidance_evals.execution import admission_decision, extract_events, judge_verdict, skill_loaded
from guidance_evals.contracts import Check, Checks


def test_admission_requires_reference_pass_base_target_failure_and_stability() -> None:
    good = Checks(checks=[Check(id="completion", passed=True), Check(id="target", passed=True, targets=["rule:sql"])])
    bad = Checks(checks=[Check(id="completion", passed=True), Check(id="target", passed=False, targets=["rule:sql"])])
    assert admission_decision([good, good], [bad, bad]) == (True, "admitted")
    assert not admission_decision([good, good], [good, good])[0]
    assert not admission_decision([good, bad], [bad, bad])[0]
    assert not admission_decision([good, good], [bad, good])[0]
    changed_evidence = good.model_copy(deep=True)
    changed_evidence.checks[0].evidence = "elapsed=0.12s"
    assert admission_decision([good, changed_evidence], [bad, bad])[0]


def test_judge_unknown_band_and_edges() -> None:
    assert judge_verdict(.8, .8, .2) is True
    assert judge_verdict(.2, .8, .2) is False
    assert judge_verdict(.5, .8, .2) is None


def test_skill_loading_uses_real_read_and_window() -> None:
    calls = [{"name": "read", "arguments": {"path": "skill://sql"}}]
    assert skill_loaded(calls, "sql", 1)
    assert not skill_loaded([{"name": "bash", "arguments": {"command": "echo skill://sql"}}], "sql", 1)
    assert not skill_loaded([{"name": "read", "arguments": {"path": "x"}}, *calls], "sql", 1)


def test_events_preserve_final_answer_and_tool_calls(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text('{"type":"tool_execution_start","toolName":"bash","args":{"command":"true"}}\n'
                      '{"type":"message_end","message":{"role":"assistant","content":[{"type":"text","text":"Done"}]}}\n')
    result = extract_events(events)
    assert result["final_answer"] == "Done"
    assert result["commands"] == [{"name": "bash", "arguments": {"command": "true"}}]


def test_provider_error_is_not_scored_as_an_agent_failure(tmp_path: Path) -> None:
    import pytest
    events = tmp_path / "events.jsonl"
    events.write_text('{"type":"message_end","message":{"role":"assistant","stopReason":"error","errorMessage":"unavailable"}}\n')
    with pytest.raises(RuntimeError, match="model request failed"):
        extract_events(events)


def test_admission_prompt_cannot_name_guidance() -> None:
    from guidance_evals.execution import prompt_names_guidance
    assert prompt_names_guidance("Follow skill://releasing", ["skill:releasing"])
    assert prompt_names_guidance("Use the permissions rule", ["rule:permissions"])
    assert not prompt_names_guidance("Fix the SQL query", ["rule:sql"])


def test_case_budget_cannot_exceed_project_limits() -> None:
    from guidance_evals.contracts import Budget
    from guidance_evals.execution import effective_budget
    budget = effective_budget(Budget(max_time="25m", max_cost=6.0), Budget(max_time="8m", max_cost=.05))
    assert budget.max_time == "8m"
    assert budget.max_cost == .05


def test_trial_token_is_redacted_and_token_bearing_diff_rejected(tmp_path: Path) -> None:
    from guidance_evals.execution import redact_artifacts
    (tmp_path / "events.jsonl").write_text('{"key":"secret-token"}\n')
    (tmp_path / "diff.patch").write_text("+secret-token\n")
    assert redact_artifacts(tmp_path, "secret-token")
    assert "secret-token" not in (tmp_path / "events.jsonl").read_text()
    assert "secret-token" not in (tmp_path / "diff.patch").read_text()
