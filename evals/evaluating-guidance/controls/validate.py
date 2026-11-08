#!/usr/bin/env python3
"""Validate control cases locally, without the evaluation engine or containers."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "project"


def verify(case: Path, candidate: Path, output: Path) -> dict:
    subprocess.run(
        ["sh", str(case / "verifier/verify.sh")],
        cwd=candidate,
        env={**os.environ, "VERIFIER_OUT": str(output), "PYTHONDONTWRITEBYTECODE": "1"},
        check=True, capture_output=True, text=True,
    )
    return json.loads((output / "checks.json").read_text())


def completion(result: dict) -> bool:
    return next(check["passed"] for check in result["checks"] if check["id"] == "completion")


def run() -> list[dict]:
    records = []
    cases = sorted((PROJECT / ".omp/evals/cases").glob("*/*/case.toml"))
    assert len(cases) >= 8, "expected six monetary and two unaffected cases"
    for manifest in cases:
        case = manifest.parent
        spec = tomllib.loads(manifest.read_text())
        record = {"case": f"{spec['family']}/{spec['id']}", "base_runs": [], "reference_runs": []}
        for variant in ("base", "reference"):
            for repeat in range(2):
                with tempfile.TemporaryDirectory(prefix="guidance-control-") as temporary:
                    candidate = Path(temporary) / "repo"
                    shutil.copytree(PROJECT, candidate, ignore=shutil.ignore_patterns(".omp", ".git", "__pycache__"))
                    if variant == "reference":
                        subprocess.run(["git", "apply", str(case / "reference.patch")], cwd=candidate, check=True, capture_output=True)
                    result = verify(case, candidate, Path(temporary) / "out")
                    if variant == "base":
                        assert not completion(result), f"{case}: unchanged seed unexpectedly completes task"
                    else:
                        assert all(check["passed"] for check in result["checks"]), f"{case}: {result}"
                    record[f"{variant}_runs"].append(result)
            assert record[f"{variant}_runs"][0] == record[f"{variant}_runs"][1], f"{case}: unstable {variant} verifier"
        if "rule:positive" in spec["targets"]:
            record["counterexamples"] = {}
            for variant, failing_id in (("missing-event", "monetary-audit"), ("banker-rounding", "cent-ties")):
                with tempfile.TemporaryDirectory(prefix="guidance-control-mutation-") as temporary:
                    candidate = Path(temporary) / "repo"
                    shutil.copytree(PROJECT, candidate, ignore=shutil.ignore_patterns(".omp", ".git", "__pycache__"))
                    subprocess.run(["git", "apply", str(case / "reference.patch")], cwd=candidate, check=True, capture_output=True)
                    changed = subprocess.run(["git", "apply", "--numstat", str(case / "reference.patch")], cwd=candidate, check=True, capture_output=True, text=True).stdout
                    paths = [line.split("\t", 2)[2] for line in changed.splitlines()]
                    assert len(paths) == 1, f"{case}: control mutation expects one changed module"
                    source = candidate / paths[0]
                    content = source.read_text()
                    if variant == "missing-event":
                        content = "".join(line for line in content.splitlines(keepends=True) if not line.lstrip().startswith('record("ledger.violet",'))
                    else:
                        content = content.replace("ROUND_HALF_UP", "ROUND_HALF_EVEN")
                    source.write_text(content)
                    result = verify(case, candidate, Path(temporary) / "out")
                    assert completion(result), f"{case}: mutation must preserve ordinary task completion"
                    failed = [check["id"] for check in result["checks"] if not check["passed"]]
                    assert failed == [failing_id], f"{case}: mutation does not isolate its targeted check: {result}"
                    record["counterexamples"][variant] = result
        if "rule:runtime" in spec["targets"]:
            with tempfile.TemporaryDirectory(prefix="guidance-control-runtime-") as temporary:
                candidate = Path(temporary) / "repo"
                shutil.copytree(PROJECT, candidate, ignore=shutil.ignore_patterns(".omp", ".git", "__pycache__"))
                subprocess.run(["git", "apply", str(case / "wrong.patch")], cwd=candidate, check=True, capture_output=True)
                result = verify(case, candidate, Path(temporary) / "out")
                assert completion(result), f"{case}: plausible wrong implementation must complete ordinary examples"
                failed = [check["id"] for check in result["checks"] if not check["passed"]]
                assert failed == ["runtime-contract"], f"{case}: wrong implementation did not isolate runtime failure"
                record["counterexamples"] = {"plausible-wrong": result}
        records.append(record)
        suffix = "; targeted counterexamples rejected" if "counterexamples" in record else ""
        print(f"{record['case']}: base FAIL x2; reference PASS x2{suffix}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the complete local checks as JSON")
    args = parser.parse_args()
    records = run()
    counterexamples = sum(len(record.get("counterexamples", {})) for record in records)
    print(f"Validated {len(records)} cases: {4 * len(records)} stable base/reference runs; {counterexamples} targeted counterexamples rejected.")
    if args.output:
        args.output.write_text(json.dumps({"cases": records}, indent=2) + "\n")


if __name__ == "__main__":
    main()
