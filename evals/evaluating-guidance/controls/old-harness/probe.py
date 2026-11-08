#!/usr/bin/env python3
"""Replay plausible-wrong runtime patches through the unchanged old grader."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from types import SimpleNamespace

CONTROLS = Path(__file__).resolve().parents[1]
PROJECT = CONTROLS / "project"
OLD_RUNNER = Path("/home/g4m3r/Documents/HuggingCar/backend/.omp/evals/run.py")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True, help="scratch evidence directory outside the skill")
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    assert not evidence.is_relative_to(CONTROLS), "keep grader evidence outside the skill"
    evidence.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("old_guidance_runner", OLD_RUNNER)
    assert spec is not None and spec.loader is not None
    old = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old
    spec.loader.exec_module(old)
    original_omp = old.omp
    current_output: Path | None = None

    def captured_omp(cwd, prompt, tools, options, extra):
        assert current_output is not None
        (current_output / "prompt.txt").write_text(prompt)
        events = original_omp(cwd, prompt, tools, options, [*extra, "--session-dir", str(current_output / "sessions")])
        (current_output / "events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))
        return events

    old.omp = captured_omp
    options = SimpleNamespace(max_time="3m", max_cost=0.25, model="anthropic/claude-opus-5-5")
    cases = json.loads((CONTROLS / "old-harness/rule-runtime.json").read_text())
    manifests = {}
    for path in (PROJECT / ".omp/evals/cases").glob("*/*/case.toml"):
        case = tomllib.loads(path.read_text())
        manifests[case["id"]] = path.parent
    results = []
    calls = 0
    for item in cases["evals"]:
        case = old.Case(target=cases["target"], **item)
        directory = manifests[case.id]
        diff = (directory / "wrong.patch").read_text()
        for replicate in range(1, 4):
            current_output = evidence / case.id / f"trial-{replicate}"
            current_output.mkdir(parents=True, exist_ok=True)
            result_path = current_output / "grading.json"
            if result_path.exists():
                result = json.loads(result_path.read_text())
            else:
                assert calls < 18, "at most eighteen paid grader calls per invocation"
                calls += 1
                with tempfile.TemporaryDirectory(prefix="runtime-old-grader-") as scratch:
                    candidate = Path(scratch) / "repo"
                    shutil.copytree(PROJECT, candidate, ignore=shutil.ignore_patterns(".omp", ".git", "AGENTS.md", "__pycache__"))
                    subprocess.run(["git", "apply", str(directory / "wrong.patch")], cwd=candidate, check=True, capture_output=True)
                    result = old.grade(case, candidate, {"answer": "Implemented the requested API. I have not executed the code or tests.", "tools": []}, diff, options)
                result.update(case=case.id, replicate=replicate)
                result_path.write_text(json.dumps(result, indent=2) + "\n")
            results.append(result)
            print(json.dumps({"case": case.id, "replicate": replicate, "passed": [check["passed"] for check in result["assertion_results"]], "cost": result["grader_cost_usd"]}), flush=True)
    summary = {"model": options.model, "max_cost_per_call": options.max_cost, "actual_cost_usd": sum(result["grader_cost_usd"] for result in results), "cases": {item["id"]: {"wrong_passes": sum(all(check["passed"] for check in result["assertion_results"]) for result in results if result["case"] == item["id"]), "trials": 3} for item in cases["evals"]}}
    (evidence / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
