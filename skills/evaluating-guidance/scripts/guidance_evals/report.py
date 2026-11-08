import math
from pathlib import Path

from .analysis import Analysis, Interval
from .store import atomic_write


def _text(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def _fixed(value: float | None, places: int) -> str:
    if value is None or not math.isfinite(value):
        return "unknown"
    text = f"{value:.{places}f}"
    return text.removeprefix("-") if float(text) == 0 else text


def _dollars(value: float | None) -> str:
    text = _fixed(value, 4)
    if text == "unknown":
        return text
    whole, fraction = text.split(".")
    text = f"{whole}.{fraction.rstrip('0').ljust(2, '0')}"
    return f"-${text[1:]}" if text.startswith("-") else f"${text}"


def _interval(value: Interval | None) -> str:
    if value is None:
        return "unknown"
    if value.low == value.high:
        return _fixed(value.low, 3)
    return f"[{_fixed(value.low, 3)}, {_fixed(value.high, 3)}]"


def markdown(result: Analysis) -> str:
    with_arm, without_arm = _text(result.with_arm), _text(result.without_arm)
    lines = ["# Guidance evaluation", "", f"**Action: {result.action}**", "", "## Verdict", "",
             "| Target | With | Without | Effect | Fixed-look bound | Verdict | Action |",
             "|---|---|---|---|---|---|---|",
             f"| {_text(result.target)} | {with_arm} | {without_arm} | {_interval(result.effect)} | {_interval(result.bound)} | {result.verdict} | {result.action} |", "",
             f"Student-t planning interval: {_interval(result.t)} (not decision authority).",
             "Bound: fixed panel, stable independent trials, two balanced looks (k=3,6), alpha=.05.",
             "Inconclusive action is a policy, not evidence of equivalence.", "", "## Per case", "",
             f"| Case | Family | {with_arm} | {without_arm} | Delta | Trials with/without | Saturated |",
             "|---|---|---|---|---|---|---|"]
    for case in result.cases:
        lines.append(f"| {_text(case.key)} | {_text(case.family)} | {_interval(case.means[result.with_arm])} | {_interval(case.means[result.without_arm])} | {_interval(case.delta)} | {case.counts[result.with_arm]}/{case.counts[result.without_arm]} | {'yes' if case.saturated else 'no'} |")
    lines.extend(["", "## Per-check separation", "",
                  f"| Check | {with_arm} | {without_arm} | Delta |", "|---|---|---|---|"])
    for check, rates in result.check_rates.items():
        first, second = rates[result.with_arm], rates[result.without_arm]
        delta = Interval(low=first.low-second.high, high=first.high-second.low)
        lines.append(f"| {_text(check)} | {_interval(first)} | {_interval(second)} | {_interval(delta)} |")
    if result.member_separation:
        lines.extend(["", "## Block member separation", "",
                      "Targeted-check fractions; default targets are case targets. Both directions are inspected.",
                      "Consistent-sign separation (absolute effect > .05 across at least two independent cases) triggers splitting, not a significance claim.",
                      "", "| Member | Effect | Bound | Cases | Direction | Split signal |", "|---|---|---|---|---|---|"])
        for member, separation in result.member_separation.items():
            lines.append(f"| {_text(member)} | {_interval(separation.effect)} | {_interval(separation.bound)} | {separation.cases} | {separation.direction} | {'yes' if separation.separates else 'no'} |")
    if result.judge_quality:
        lines.extend(["", "## Judged questions", "",
                      "High unknown or disagreement rates mean the question is ambiguous; rewrite it in a new case.",
                      "", "| Question | Trials | Unknown | Judges disagree |", "|---|---|---|---|"])
        for question, quality in result.judge_quality.items():
            disagree = f"{quality.disagreements}/{quality.compared}" if quality.compared else "—"
            lines.append(f"| {_text(question)} | {quality.trials} | {quality.unknown}/{quality.trials} | {disagree} |")
    lines.extend(["", "## Cost and reliability", "",
                  "Deltas are with minus without, equally weighted per case.", "",
                  f"- Cost delta: {_dollars(result.cost_delta)}", f"- Tokens delta: {_fixed(result.tokens_delta, 0)}",
                  f"- Time delta (seconds): {_fixed(result.seconds_delta, 1)}"])
    for arm, exposure in result.exposure.items():
        lines.append(f"- {_text(arm)} exposure: {exposure.exposed}/{exposure.total}; unknown: {exposure.unknown}")
        lines.append(f"- {_text(arm)} pass^{result.reliability_k}: {_interval(result.pass_k[arm])}")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {_text(warning)}" for warning in result.warnings)
    if not result.warnings:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def write_report(result: Analysis, directory: Path) -> tuple[Path, Path]:
    md, data = directory / "report.md", directory / "report.json"
    atomic_write(md, markdown(result).encode())
    atomic_write(data, (result.model_dump_json(indent=2) + "\n").encode())
    return md, data
