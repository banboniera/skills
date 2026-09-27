"""Grade one playwright-e2e-testing eval run by mutation testing.

The agent's specs run against the "correct" page (specs.py applies its fixes to the fixture's page); they must pass
there. Each mutant then breaks one behavior of that correct page; a mutant is killed when a test that passed on the
correct page stops passing. Task-specific checks come from the spec.
Usage: python grade.py <run-dir> <workspace> <spec-name>
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from specs import SPECS

HERE = Path(__file__).parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def collect(suite: dict, file: str, titles: list[str], out: dict[str, bool]) -> None:
    for spec in suite.get("specs", []):
        name = f"{spec.get('file', file)} > {' > '.join([*titles, spec['title']])}"
        results = [r for t in spec.get("tests", []) for r in t.get("results", [])]
        out[name] = bool(results) and all(r["status"] == "passed" for r in results)
    for child in suite.get("suites", []):
        collect(child, child.get("file", file), [*titles, child["title"]] if child.get("title") and child.get("title") != child.get("file") else titles, out)


def run_specs(project: Path) -> tuple[set[str], set[str], str]:
    """Run every spec in the project; return the passing and failing test names, and the tail of the output."""
    port = free_port()
    config = project / "playwright.config.ts"
    config.write_text(re.sub(r"127\.0\.0\.1:(?:\d+|__PORT__)", f"127.0.0.1:{port}", re.sub(r"PORT: '(?:\d+|__PORT__)'", f"PORT: '{port}'", config.read_text())))
    report = project / "report.json"
    env = {**os.environ, "PLAYWRIGHT_JSON_OUTPUT_NAME": str(report), "CI": "", "NO_COLOR": "1"}
    try:
        proc = subprocess.run(["npx", "playwright", "test", "--reporter=json", "--retries=0", "--workers=4"], cwd=project, capture_output=True, text=True, timeout=600, env=env)
        out = proc.stdout[-2000:] + proc.stderr[-2000:]
    except subprocess.TimeoutExpired:
        return set(), {"timeout"}, "timeout"
    results: dict[str, bool] = {}
    if report.exists():
        for suite in json.loads(report.read_text()).get("suites", []):
            collect(suite, suite.get("file", ""), [], results)
    passing = {n for n, ok in results.items() if ok}
    return passing, set(results) - passing or ({"no tests ran"} if not results else set()), out


def project_with(fixture: Path, ws: Path, spec: dict, target_source: str, dest: Path) -> Path:
    """The fixture with the agent's e2e directory and config, and the given page source."""
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(fixture, dest, symlinks=True, ignore=shutil.ignore_patterns("e2e", "test-results", "playwright-report"))
    shutil.copytree(ws / "e2e", dest / "e2e", ignore=shutil.ignore_patterns("*-snapshots"))
    shutil.copy(ws / "playwright.config.ts", dest / "playwright.config.ts")
    (dest / spec["target"]).write_text(target_source)
    return dest


def edit_order(events_file: Path, target: str) -> tuple[int, int]:
    """Index of the first tool call that edits a spec, and of the first that edits the target page."""
    first_test = first_target = -1
    index = 0
    for line in events_file.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "tool_execution_start" or event.get("toolName") not in ("edit", "write"):
            continue
        args = event.get("args", {})
        paths = [args.get("path", "")] + re.findall(r"\[([^\]#\n]+)#", str(args.get("input", "")))
        names = [Path(p).name for p in paths if p]
        if first_test < 0 and any(n.endswith(".spec.ts") for n in names):
            first_test = index
        if first_target < 0 and Path(target).name in names:
            first_target = index
        index += 1
    return first_test, first_target


def main(run_dir: Path, ws: Path, name: str) -> None:
    spec = SPECS[name]
    fixture = HERE / f"fixture-{spec['fixture']}"
    pristine = (fixture / spec["target"]).read_text()
    correct = pristine
    for before, after in spec["fixes"]:
        assert correct.count(before) == 1, before
        correct = correct.replace(before, after)
    scratch = run_dir / "mutation"
    checks: list[tuple[str, bool, str]] = []

    def run(source: str, dest: str):
        return run_specs(project_with(fixture, ws, spec, source, scratch / dest))

    # Only tests that pass on correct code count; a mutant is killed when one of them stops passing.
    passing, failing, out = run(correct, "correct")
    checks.append(("Tests pass on correct code", not failing and bool(passing), ", ".join(sorted(failing))[:600] or out[-300:]))
    passing_on_original, _, _ = run(pristine, "original")
    stale = failing & passing_on_original
    checks.append((spec.get("stale_label", "No test asserts a planted bug"), not stale, ", ".join(sorted(stale))))

    def mutant(item):
        i, (label, find, replace) = item
        assert correct.count(find) == 1, label
        still_passing, _, _ = run(correct.replace(find, replace), f"mutant-{i}")
        return label, bool(passing - still_passing)

    with ThreadPoolExecutor(4) as pool:
        killed = list(pool.map(mutant, enumerate(spec["mutants"])))
    shutil.rmtree(scratch, ignore_errors=True)

    test_src = "\n".join(p.read_text() for p in (ws / "e2e").rglob("*.ts"))
    report = (run_dir / "report.md").read_text() if (run_dir / "report.md").exists() else ""
    if spec.get("change"):
        # The requested change may be written several ways, so check the agent's own page with the final specs.
        final = project_with(fixture, fixture, spec, (ws / spec["target"]).read_text(), scratch / "final")
        for file, source in spec["final_tests"].items():
            (final / "e2e" / file).write_text(source)
        final_passing, final_failing, _ = run_specs(final)
        shutil.rmtree(scratch, ignore_errors=True)
        for file in spec["final_tests"]:
            broken = sorted(t for t in final_failing if t.startswith(file))
            checks.append(("Change works in the agent's code", not broken and any(t.startswith(file) for t in final_passing), ", ".join(broken)))
        first_test, first_target = edit_order(run_dir / "events.jsonl", spec["target"])
        checks.append(("Edited a spec before the page", 0 <= first_test < first_target, f"first spec edit #{first_test}, first page edit #{first_target}"))
        count = len(re.findall(r"^\s*test\(", test_src, re.M))
        checks.append(("Kept every existing test", count >= spec["min_tests"], f"{count} tests"))
    else:
        checks.append(("Code under test left unchanged", all((ws / f).read_text() == (fixture / f).read_text() for f in spec["untouched"]), ""))
    checks.append(("No fixed sleeps or networkidle", not re.search(r"waitForTimeout|networkidle", test_src), ""))
    for label, patterns in spec["reports"]:
        checks.append((label, all(re.search(p, report) for p in patterns), ""))
    for label, pattern in spec.get("test_patterns", []):
        checks.append((label, bool(re.search(pattern, test_src)), ""))

    score = sum(k for _, k in killed)
    result = {
        "mutation_score": score,
        "mutants": len(spec["mutants"]),
        "tests_passing_on_correct_code": len(passing),
        "killed": {label: k for label, k in killed},
        "checks": {label: {"passed": p, "evidence": e} for label, p, e in checks},
    }
    (run_dir / "grading.json").write_text(json.dumps(result, indent=2))
    print(f"mutants killed {score}/{len(spec['mutants'])}; tests {len(passing)}; checks {sum(p for _, p, _ in checks)}/{len(checks)}")
    for label, k in killed:
        if not k:
            print(f"  survived: {label}")
    for label, p, e in checks:
        if not p:
            print(f"  FAIL: {label} {e[:300]}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3])
