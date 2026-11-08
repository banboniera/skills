import json
from pathlib import Path

import pytest

from guidance_evals.analysis import Interval, analyze
from guidance_evals.report import markdown, write_report


@pytest.mark.parametrize(("cost", "tokens", "seconds", "cost_text", "tokens_text", "seconds_text"), [
    (0.001234567, 1234.499999, 1.234567, "$0.0012", "1234", "1.2"),
    (-0.001234567, -1234.499999, -1.234567, "-$0.0012", "-1234", "-1.2"),
    (1.23000000001, 12.00000000001, 0.30000000004, "$1.23", "12", "0.3"),
    (-0.00000001, -0.00000001, -0.00000001, "$0.00", "0", "0.0"),
    (None, None, None, "unknown", "unknown", "unknown"),
])
def test_markdown_metric_units_and_precision(
    cost: float | None, tokens: float | None, seconds: float | None,
    cost_text: str, tokens_text: str, seconds_text: str,
) -> None:
    result = analyze([], "with", "without").model_copy(update={
        "cost_delta": cost, "tokens_delta": tokens, "seconds_delta": seconds,
    })
    text = markdown(result)
    assert f"- Cost delta: {cost_text}\n" in text
    assert f"- Tokens delta: {tokens_text}\n" in text
    assert f"- Time delta (seconds): {seconds_text}\n" in text


def test_markdown_warnings_stay_on_one_line_and_intervals_avoid_negative_zero() -> None:
    result = analyze([], "with", "without").model_copy(update={
        "effect": Interval(low=-0.00000001, high=0.0),
        "warnings": ["First line\n\rsecond line\tthird line", "Caution: fixed panel only."],
    })
    text = markdown(result)
    assert "-0.000" not in text
    assert "- First line second line third line\n" in text
    assert "- Caution: fixed panel only.\n" in text
    assert "stable independent trials" in text
    assert "not evidence of equivalence" in text


def test_report_json_preserves_raw_numeric_metrics(tmp_path: Path) -> None:
    result = analyze([], "with", "without").model_copy(update={
        "cost_delta": 0.00123456789, "tokens_delta": -2.5, "seconds_delta": None,
    })
    md, data = write_report(result, tmp_path)
    payload = json.loads(data.read_text())
    assert payload["cost_delta"] == 0.00123456789
    assert payload["tokens_delta"] == -2.5
    assert payload["seconds_delta"] is None
    assert "- Cost delta: $0.0012\n" in md.read_text()
