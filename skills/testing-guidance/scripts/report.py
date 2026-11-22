#!/usr/bin/env python3
"""Aggregate a trial iteration into benchmark.json, benchmark.md and a self-contained report.html.

Usage: report.py <iteration-dir> [--previous <iteration-dir>]

Reads index.json and each run's metrics.json, checks.json and grading.json (grading is
optional: ungraded runs count for checks, cost and time only).
"""

from __future__ import annotations

import argparse
import html as h
import json
import statistics
from pathlib import Path
from typing import Any

METRICS = ("expectations", "checks", "seconds", "cost", "tokens")


def stats(values: list[float]) -> dict:
    if not values:
        return {"mean": None, "stddev": None, "n": 0}
    return {"mean": round(statistics.fmean(values), 4), "stddev": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0, "n": len(values)}


def load_run(out: Path, run: dict) -> dict:
    d = out / run["dir"]
    metrics = json.loads((d / "metrics.json").read_text())
    checks = json.loads((d / "checks.json").read_text()) if (d / "checks.json").exists() else []
    grading = json.loads((d / "grading.json").read_text()) if (d / "grading.json").exists() else None
    return {**run, "metrics": metrics, "checks": checks, "grading": grading}


def loaded(metrics: dict, kind: str, name: str) -> bool:
    loads = metrics.get("loads", {})
    if kind == "skill":
        return name in loads.get("skills", [])
    if kind == "rule":
        return name in loads.get("rules", [])
    return bool(loads.get("command_expanded"))


def rate(items: list[bool]) -> float | None:
    return sum(items) / len(items) if items else None


def benchmark(out: Path) -> dict:
    index = json.loads((out / "index.json").read_text())
    kind, name, arms = index["kind"], index["name"], index["arms"]
    runs = [load_run(out, r) for r in index["runs"] if r.get("status") == "done"]
    summary: dict[str, Any] = {}
    for arm in arms:
        mine = [r for r in runs if r["arm"] == arm]
        exp = [rate([e["passed"] for e in r["grading"]["expectations"]]) for r in mine if r["grading"]]
        chk = [rate([c["passed"] for c in r["checks"]]) for r in mine]
        summary[arm] = {
            "runs": len(mine),
            "graded": len(exp),
            "expectations": stats([x for x in exp if x is not None]),
            "checks": stats([x for x in chk if x is not None]),
            "seconds": stats([r["metrics"]["seconds"] for r in mine]),
            "cost": stats([r["metrics"]["cost"] for r in mine]),
            "tokens": stats([float(sum(r["metrics"]["tokens"].values())) for r in mine]),
            "loaded": rate([loaded(r["metrics"], kind, name) for r in mine]),
            "failed_exits": sum(r["metrics"]["exit_code"] != 0 for r in mine),
        }
    items = []
    for ev in index["evals"]:
        ev_runs = [r for r in runs if r["eval"] == ev]
        names: dict[tuple[str, str], None] = {}
        for r in ev_runs:
            for e in (r["grading"] or {}).get("expectations", []):
                names[("expectation", e["text"])] = None
            for c in r["checks"]:
                names[("check", c["name"])] = None
        for item_kind, item in names:
            per_arm: dict[str, list[bool]] = {arm: [] for arm in arms}
            for r in ev_runs:
                pool = (r["grading"] or {}).get("expectations", []) if item_kind == "expectation" else r["checks"]
                key = "text" if item_kind == "expectation" else "name"
                per_arm[r["arm"]] += [x["passed"] for x in pool if x[key] == item]
            rates = {arm: rate(v) for arm, v in per_arm.items()}
            items.append({"eval": ev, "kind": item_kind, "name": item, "rates": rates, "flag": flag(rates, per_arm)})
    return {"target": index["target"], "kind": kind, "name": name, "model": index.get("model"), "arms": summary,
            "items": items, "spent": index.get("spent"), "stopped": index.get("stopped"),
            "references": index.get("references", []), "shadowed": index.get("shadowed_in_without", []),
            "skipped": sum(r.get("status") != "done" for r in index["runs"])}


def flag(rates: dict[str, float | None], per_arm: dict[str, list[bool]]) -> str | None:
    """Why an expectation or check tells little: it varies by chance, or no arm differs."""
    known = [v for v in rates.values() if v is not None]
    if any(0 < (rate(v) or 0) < 1 for v in per_arm.values() if len(v) > 1):
        return "varies within an arm"
    if len(known) > 1 and len(set(known)) == 1:
        return "never passes" if known[0] == 0 else "same in every arm"
    return None


def deltas(current: dict, previous: dict) -> dict:
    out: dict[str, dict] = {}
    for arm, s in current["arms"].items():
        before = previous.get("arms", {}).get(arm)
        if not before:
            continue
        out[arm] = {}
        for m in METRICS:
            a, b = s[m]["mean"], before[m]["mean"]
            out[arm][m] = round(a - b, 4) if a is not None and b is not None else None
    return out


def fmt(s: dict, pct: bool = False) -> str:
    if s["mean"] is None:
        return "-"
    if pct:
        return f"{s['mean'] * 100:.0f}% ± {s['stddev'] * 100:.0f}"
    return f"{s['mean']:.2f} ± {s['stddev']:.2f}"


def markdown(b: dict, delta: dict | None) -> str:
    lines = [f"# Benchmark: {b['kind']} {b['name']}", "", f"Model: {b['model'] or 'session default'}; spent ${b['spent']}"]
    if b["stopped"]:
        lines.append(f"Stopped early: {b['stopped']}")
    if b["references"]:
        lines.append("Installed in every arm, without included, and pointing at the target: " + ", ".join(b["references"]))
    if b["shadowed"]:
        lines.append("Hidden in the without arm because they point at the target: " + ", ".join(b["shadowed"]))
    lines += ["", "| Arm | Runs | Loaded | Expectations | Checks | Seconds | Cost USD | Tokens |", "|---|---|---|---|---|---|---|---|"]
    for arm, s in b["arms"].items():
        load = "-" if s["loaded"] is None else f"{s['loaded'] * 100:.0f}%"
        lines.append(f"| {arm} | {s['runs']} | {load} | {fmt(s['expectations'], True)} | {fmt(s['checks'], True)} | "
                     f"{fmt(s['seconds'])} | {fmt(s['cost'])} | {fmt(s['tokens'])} |")
    if delta:
        lines += ["", "Change against the previous iteration (mean):", ""]
        for arm, d in delta.items():
            lines.append(f"- {arm}: " + ", ".join(f"{k} {v:+}" for k, v in d.items() if v is not None))
    flagged = [i for i in b["items"] if i["flag"]]
    if flagged:
        lines += ["", "## Flagged expectations and checks", ""]
        lines += [f"- {i['eval']} {i['kind']} \"{i['name']}\": {i['flag']} ({rates_text(i['rates'])})" for i in flagged]
    return "\n".join(lines) + "\n"


def rates_text(rates: dict) -> str:
    return ", ".join(f"{arm} {'-' if v is None else f'{v * 100:.0f}%'}" for arm, v in rates.items())


CSS = """body{font:14px/1.45 system-ui,sans-serif;margin:2em;max-width:1200px}table{border-collapse:collapse;margin:1em 0}
td,th{border:1px solid #8884;padding:4px 8px;text-align:left;vertical-align:top}pre{white-space:pre-wrap;background:#8881;padding:8px;max-height:40em;overflow:auto}
.pass{color:#1a7f37}.fail{color:#cf222e}details{margin:.4em 0}summary{cursor:pointer}.flag{color:#9a6700}"""


def html(b: dict, out: Path, delta: dict | None) -> str:
    e = h.escape
    parts = [f"<!doctype html><meta charset=utf-8><title>{e(b['name'])} benchmark</title><style>{CSS}</style>",
             f"<h1>{e(b['kind'])} {e(b['name'])}</h1><p>Model: {e(str(b['model'] or 'session default'))}; spent ${b['spent']}"
             + (f"; stopped early: {e(b['stopped'])}" if b["stopped"] else "") + "</p>",
             "<table><tr><th>Arm<th>Runs<th>Loaded<th>Expectations<th>Checks<th>Seconds<th>Cost USD<th>Tokens"]
    for arm, s in b["arms"].items():
        load = "-" if s["loaded"] is None else f"{s['loaded'] * 100:.0f}%"
        d = (delta or {}).get(arm, {})
        change = "".join(f"<br><small>{k} {v:+}</small>" for k, v in d.items() if v)
        parts.append(f"<tr><td>{e(arm)}{change}<td>{s['runs']}<td>{load}<td>{fmt(s['expectations'], True)}<td>{fmt(s['checks'], True)}"
                     f"<td>{fmt(s['seconds'])}<td>{fmt(s['cost'])}<td>{fmt(s['tokens'])}")
    parts.append("</table><h2>Expectations and checks</h2><table><tr><th>Eval<th>Kind<th>Name<th>Pass rate by arm<th>Flag")
    for i in b["items"]:
        parts.append(f"<tr><td>{e(i['eval'])}<td>{i['kind']}<td>{e(i['name'])}<td>{e(rates_text(i['rates']))}"
                     f"<td class=flag>{e(i['flag'] or '')}")
    parts.append("</table><h2>Runs</h2>")
    index = json.loads((out / "index.json").read_text())
    for ev, spec in index["evals"].items():
        parts.append(f"<h3>{e(ev)}</h3><pre>{e(spec['prompt'])}</pre>")
        for run in [r for r in index["runs"] if r["eval"] == ev]:
            if run.get("status") != "done":
                parts.append(f"<p>{e(run['arm'])} #{run['rep']}: {e(run['status'])}</p>")
                continue
            parts.append(run_html(load_run(out, run), out / run["dir"]))
    return "\n".join(parts)


def run_html(run: dict, d: Path) -> str:
    e = h.escape
    m = run["metrics"]
    grades = (run["grading"] or {}).get("expectations", [])
    passed = sum(g["passed"] for g in grades) + sum(c["passed"] for c in run["checks"])
    total = len(grades) + len(run["checks"])
    loads = m.get("loads", {})
    rows = "".join(f"<tr><td class={'pass' if g['passed'] else 'fail'}>{'pass' if g['passed'] else 'fail'}"
                   f"<td>{e(g['text'])}<td>{e(str(g.get('p_yes', '')))}<td>{e(g.get('evidence') or '')}" for g in grades)
    rows += "".join(f"<tr><td class={'pass' if c['passed'] else 'fail'}>{'pass' if c['passed'] else 'fail'}"
                    f"<td>check: {e(c['name'])}<td>exit {c['exit_code']}<td><pre>{e(c['output'][-1500:])}</pre>" for c in run["checks"])
    diff = (d / "diff.patch").read_text() if (d / "diff.patch").exists() else ""
    return (f"<details><summary><b>{e(run['arm'])} #{run['rep']}</b>: {passed}/{total} passed, exit {m['exit_code']}, "
            f"${m['cost']:.2f}, {m['seconds']}s, loaded skills {e(', '.join(loads.get('skills', [])) or '-')}, "
            f"rules {e(', '.join(loads.get('rules', [])) or '-')}</summary>"
            f"<p>Prompt:</p><pre>{e(m.get('prompt', ''))}</pre>"
            f"<table><tr><th>Result<th>Expectation or check<th>P(yes)<th>Evidence{rows}</table>"
            f"<p>Final answer:</p><pre>{e((d / 'final.md').read_text())}</pre>"
            f"<details><summary>Diff ({len(diff.splitlines())} lines)</summary><pre>{e(diff[:100_000])}</pre></details>"
            f"<p>Tool calls: {e(json.dumps(m.get('tool_calls', {})))}; session: {e(str(d / 'session'))}</p></details>")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    b = benchmark(args.out)
    delta = deltas(b, json.loads((args.previous / "benchmark.json").read_text())) if args.previous else None
    (args.out / "benchmark.json").write_text(json.dumps({**b, "delta": delta}, indent=2))
    (args.out / "benchmark.md").write_text(markdown(b, delta))
    (args.out / "report.html").write_text(html(b, args.out, delta))
    print((args.out / "benchmark.md").read_text())
    print(f"report: {args.out / 'report.html'}")


if __name__ == "__main__":
    main()
