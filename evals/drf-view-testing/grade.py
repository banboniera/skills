"""Grade one drf-view-testing eval run by mutation testing.

The agent's tests run against the "correct" target file (specs.py applies its fixes to the fixture's file); they
must pass there. Each mutant then breaks one behavior of that correct file; a mutant is killed when a test that
passed on the correct file stops passing. Task-specific checks come from the spec.
Usage: python grade.py <run-dir> <workspace> <spec-name> <python>
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from specs import SPECS


def run_tests(project: Path, python: str, app: str) -> tuple[set[str], set[str], str]:
    """Return the ids of passing and of failing tests, and the tail of the output."""
    try:
        proc = subprocess.run([python, "manage.py", "test", app, "--noinput", "-v", "2"], cwd=project, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return set(), {"timeout"}, "timeout"
    # "name (dotted.id) ... status", with an optional docstring line before the dots; the first line may follow migration output.
    results = re.findall(r"(\w+) \(([\w.]+)\)\n?[^\n]*?\.\.\. (ok|FAIL|ERROR|skipped|expected failure|unexpected success)", proc.stderr)
    passing = {test for _, test, status in results if status == "ok"}
    failing = {test for _, test, status in results if status != "ok"}
    failing |= set(re.findall(r"^ERROR: (\w+ \([\w.]+\))", proc.stderr, re.M)) - {""}
    return passing, failing, proc.stderr[-3000:]


def project_with(fixture: Path, spec: dict, tests: Path, target_source: str, dest: Path) -> Path:
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(fixture, dest)
    shutil.rmtree(dest / spec["app"] / "tests")
    shutil.copytree(tests, dest / spec["app"] / "tests")
    (dest / spec["target"]).write_text(target_source)
    return dest


def edit_order(events_file: Path, spec: dict) -> tuple[int, int]:
    """Index of the first tool call that edits a test file, and of the first that edits the target file."""
    first_test = first_target = -1
    index = 0
    for line in events_file.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "tool_execution_start" or event.get("toolName") not in ("edit", "write"):
            continue
        # Edited paths come from "path" arguments and from "[path#hash]" headers in edit inputs; they may be relative to any directory.
        args = event.get("args", {})
        paths = [args.get("path", "")] + re.findall(r"\[([^\]#\n]+)#", str(args.get("input", "")))
        names = [Path(p).name for p in paths if p]
        if first_test < 0 and any(n.startswith("test") for n in names):
            first_test = index
        if first_target < 0 and Path(spec["target"]).name in names:
            first_target = index
        index += 1
    return first_test, first_target


def main(run_dir: Path, ws: Path, name: str, python: str) -> None:
    spec = SPECS[name]
    fixture = Path(__file__).parent / f"fixture-{spec['fixture']}"
    pristine = (fixture / spec["target"]).read_text()
    correct = pristine
    for before, after in spec["fixes"]:
        assert correct.count(before) == 1, before
        correct = correct.replace(before, after)
    tests = ws / spec["app"] / "tests"
    scratch = run_dir / "mutation"
    checks: list[tuple[str, bool, str]] = []

    def run(source: str, dest: str):
        return run_tests(project_with(fixture, spec, tests, source, scratch / dest), python, spec["app"])

    # Only tests that pass on correct code count; a mutant is killed when one of them stops passing.
    passing, failing, out = run(correct, "correct")
    checks.append(("Tests pass on correct code", not failing and bool(passing), ", ".join(sorted(failing)) or out[-300:]))
    passing_on_original, _, _ = run(pristine, "original")
    stale = failing & passing_on_original
    checks.append((spec.get("stale_label", "No test asserts a planted bug"), not stale, ", ".join(sorted(stale))))
    killed = []
    for label, find, replace in spec["mutants"]:
        assert correct.count(find) == 1, label
        still_passing, _, _ = run(correct.replace(find, replace), "mutant")
        killed.append((label, bool(passing - still_passing)))
    shutil.rmtree(scratch, ignore_errors=True)

    test_src = "\n".join(p.read_text() for p in tests.rglob("*.py"))
    report = (run_dir / "report.md").read_text() if (run_dir / "report.md").exists() else ""
    if spec.get("change"):
        # The requested change may be written several ways, so check the agent's own code with the final tests.
        final = project_with(fixture, spec, fixture / spec["app"] / "tests", (ws / spec["target"]).read_text(), scratch / "final")
        for name, source in spec["final_tests"].items():
            (final / spec["app"] / "tests" / name).write_text(source)
        final_passing, final_failing, _ = run_tests(final, python, spec["app"])
        shutil.rmtree(scratch, ignore_errors=True)
        for name in spec["final_tests"]:
            prefix = f"{spec['app']}.tests.{name[:-3]}."
            broken = sorted(t for t in final_failing if t.startswith(prefix))
            checks.append(("Change works in the agent's code", not broken and any(t.startswith(prefix) for t in final_passing), ", ".join(broken)))
        first_test, first_target = edit_order(run_dir / "events.jsonl", spec)
        checks.append(("Edited a test before the view", 0 <= first_test < first_target, f"first test edit #{first_test}, first view edit #{first_target}"))
        count = len(re.findall(r"^\s*def test_", test_src, re.M))
        checks.append(("Kept every existing test", count >= spec["min_tests"], f"{count} tests"))
    else:
        checks.append(("Code under test left unchanged", all((ws / f).read_text() == (fixture / f).read_text() for f in spec["untouched"]), ""))
    checks.append(("No assertRaises(Exception)", not re.search(r"assertRaises\(\s*Exception\s*[,)]", test_src), ""))
    for label, patterns in spec["reports"]:
        checks.append((label, all(re.search(p, report) for p in patterns), ""))
    if spec.get("base_class"):
        checks.append(("Uses the project's test base", spec["base_class"] in test_src, ""))

    score = sum(k for _, k in killed)
    result = {
        "mutation_score": score,
        "mutants": len(spec["mutants"]),
        "tests_passing_on_correct_code": len(passing),
        "killed": {label: k for label, k in killed},
        "checks": {label: {"passed": p, "evidence": e} for label, p, e in checks},
    }
    (run_dir / "grading.json").write_text(json.dumps(result, indent=2))
    print(f"mutants killed {score}/{len(spec['mutants'])}; checks {sum(p for _, p, _ in checks)}/{len(checks)}")
    for label, k in killed:
        if not k:
            print(f"  survived: {label}")
    for label, p, e in checks:
        if not p:
            print(f"  FAIL: {label} {e[:300]}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4])
