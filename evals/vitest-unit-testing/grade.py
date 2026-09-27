"""Grade one vitest-unit-testing eval run by mutation testing.

The agent's tests run against the "correct" sources (specs.py applies its fixes to the fixture); they must pass there.
Each mutant then breaks one behavior of the correct sources; a mutant is killed when a test that passed on the correct
sources stops passing. Task-specific checks come from the spec.
Usage: python grade.py <run-dir> <workspace> <spec-name>
"""

import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from specs import SPECS

HERE = Path(__file__).parent
TEST = re.compile(r"\.(test|spec)\.(ts|tsx)$")


def run_tests(project: Path) -> tuple[set[str], set[str], str]:
    """Run every test in the project; return the passing and failing test names, and the tail of the output."""
    report = project / "report.json"
    env = {**os.environ, "CI": "1", "NO_COLOR": "1", "FORCE_COLOR": "0"}
    try:
        proc = subprocess.run(["npx", "vitest", "run", "--reporter=json", f"--outputFile={report}"], cwd=project, capture_output=True, text=True, timeout=600, env=env)
        out = proc.stdout[-2000:] + proc.stderr[-2000:]
    except subprocess.TimeoutExpired:
        return set(), {"timeout"}, "timeout"
    passing: set[str] = set()
    failing: set[str] = set()
    if report.exists():
        for file in json.loads(report.read_text()).get("testResults", []):
            name = os.path.relpath(file["name"], project)
            results = file.get("assertionResults", [])
            if not results and file.get("status") == "failed":
                failing.add(f"{name} (file failed to run)")
            for test in results:
                (passing if test["status"] == "passed" else failing).add(f"{name} > {test['fullName']}")
    if not passing and not failing:
        failing.add("no tests ran")
    return passing, failing, out


def project_with(fixture: Path, tests_from: Path, sources: dict[str, str], dest: Path) -> Path:
    """The fixture without its tests, with every test file from `tests_from` and the given source files."""
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(fixture, dest, symlinks=True, ignore=lambda d, names: [n for n in names if TEST.search(n)])
    for test in (tests_from / "src").rglob("*"):
        if TEST.search(test.name) and "node_modules" not in test.parts:
            target = dest / test.relative_to(tests_from)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(test, target)
    for file, source in sources.items():
        (dest / file).write_text(source)
    return dest


def edit_order(events_file: Path, target: str) -> tuple[int, int]:
    """Index of the first tool call that edits a test, and of the first that edits the target file."""
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
        if first_test < 0 and any(TEST.search(n) for n in names):
            first_test = index
        if first_target < 0 and Path(target).name in names:
            first_target = index
        index += 1
    return first_test, first_target


def main(run_dir: Path, ws: Path, name: str) -> None:
    spec = SPECS[name]
    fixture = HERE / f"fixture-{spec['fixture']}"
    pristine: dict[str, str] = {}
    correct: dict[str, str] = {}
    for file, before, after in spec["fixes"]:
        source = correct.get(file) or (fixture / file).read_text()
        pristine.setdefault(file, (fixture / file).read_text())
        assert source.count(before) == 1, before
        correct[file] = source.replace(before, after)
    for _, file, _, _ in spec["mutants"]:
        pristine.setdefault(file, (fixture / file).read_text())
        correct.setdefault(file, pristine[file])
    scratch = run_dir / "mutation"
    checks: list[tuple[str, bool, str]] = []

    def run(sources: dict[str, str], dest: str):
        return run_tests(project_with(fixture, ws, sources, scratch / dest))

    # Only tests that pass on correct code count; a mutant is killed when one of them stops passing.
    passing, failing, out = run(correct, "correct")
    checks.append(("Tests pass on correct code", not failing and bool(passing), ", ".join(sorted(failing))[:600] or out[-300:]))
    passing_on_original, _, _ = run(pristine, "original")
    stale = failing & passing_on_original
    checks.append((spec.get("stale_label", "No test asserts a planted bug"), not stale, ", ".join(sorted(stale))[:600]))

    def mutant(item):
        i, (label, file, find, replace) = item
        assert correct[file].count(find) == 1, label
        still_passing, _, _ = run({**correct, file: correct[file].replace(find, replace)}, f"mutant-{i}")
        return label, bool(passing - still_passing)

    with ThreadPoolExecutor(6) as pool:
        killed = list(pool.map(mutant, enumerate(spec["mutants"])))
    shutil.rmtree(scratch, ignore_errors=True)

    tests = [p for p in (ws / "src").rglob("*") if TEST.search(p.name)]
    test_src = "\n".join(p.read_text() for p in tests)
    report = (run_dir / "report.md").read_text() if (run_dir / "report.md").exists() else ""
    if spec.get("change"):
        # The requested change may be written several ways, so check the agent's own code with the final tests.
        final = project_with(fixture, fixture, {spec["target"]: (ws / spec["target"]).read_text()}, scratch / "final")
        for file, source in spec["final_tests"].items():
            (final / file).write_text(source)
        final_passing, final_failing, _ = run_tests(final)
        shutil.rmtree(scratch, ignore_errors=True)
        for file in spec["final_tests"]:
            broken = sorted(t for t in final_failing if t.startswith(file))
            checks.append(("Change works in the agent's code", not broken and any(t.startswith(file) for t in final_passing), ", ".join(broken)))
        first_test, first_target = edit_order(run_dir / "events.jsonl", spec["target"])
        checks.append(("Edited a test before the code", 0 <= first_test < first_target, f"first test edit #{first_test}, first code edit #{first_target}"))
        count = len(re.findall(r"^\s*(?:it|test)(?:\.each\([\s\S]*?\))?\(", test_src, re.M))
        checks.append(("Kept every existing test", count >= spec["min_tests"], f"{count} tests"))
    else:
        checks.append(("Code under test left unchanged", all((ws / f).read_text() == (fixture / f).read_text() for f in spec["untouched"]), ""))
    for label, patterns in spec["reports"]:
        checks.append((label, all(re.search(p, report) for p in patterns), ""))

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
