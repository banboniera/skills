import importlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
checks = []
module = importlib.import_module("parcelbill.code_counts")

def run(identifier, operation, targets=()):
    try:
        operation()
        passed, evidence = True, "runtime behavior matched"
    except (AssertionError, AttributeError) as exc:
        passed, evidence = False, type(exc).__name__ + ": " + str(exc)
    checks.append({"id": identifier, "passed": passed, "critical": True, "evidence": evidence, "targets": list(targets)})

def completion():
    fn = getattr(module, "count_codes")
    assert fn(iter(["A", "B", "A"])) == [{"type": "string", "value": "A", "count": 2}, {"type": "string", "value": "B", "count": 1}]
    assert fn(iter([])) == []

def runtime():
    fn = getattr(module, "count_codes")
    result = fn(iter([True, 1, False, 0, "1", 1, True]))
    assert result == [{"type": "boolean", "value": True, "count": 2}, {"type": "integer", "value": 1, "count": 2}, {"type": "boolean", "value": False, "count": 1}, {"type": "integer", "value": 0, "count": 1}, {"type": "string", "value": "1", "count": 1}]

run("completion", completion)
run("runtime-contract", runtime, ["rule:runtime"])
output = Path(os.environ.get("VERIFIER_OUT", "/verifier-out"))
output.mkdir(parents=True, exist_ok=True)
(output / "checks.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
print(json.dumps({"checks": checks}))
