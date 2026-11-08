import importlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
checks = []
module = importlib.import_module("parcelbill.status_groups")

def run(identifier, operation, targets=()):
    try:
        operation()
        passed, evidence = True, "runtime behavior matched"
    except (AssertionError, AttributeError) as exc:
        passed, evidence = False, type(exc).__name__ + ": " + str(exc)
    checks.append({"id": identifier, "passed": passed, "critical": True, "evidence": evidence, "targets": list(targets)})

def completion():
    fn = getattr(module, "collect_status_groups")
    assert fn(iter([])) == {}
    assert isinstance(fn(iter([{"status": "ready", "code": "A"} ])), dict)

def runtime():
    fn = getattr(module, "collect_status_groups")
    events = iter([{"status": "held", "code": "A"}, {"status": "held", "code": "B"}, {"status": "ready", "code": "C"}])
    assert fn(events) == {"held": ["A", "B"], "ready": ["C"]}

run("completion", completion)
run("runtime-contract", runtime, ["rule:runtime"])
output = Path(os.environ.get("VERIFIER_OUT", "/verifier-out"))
output.mkdir(parents=True, exist_ok=True)
(output / "checks.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
print(json.dumps({"checks": checks}))
