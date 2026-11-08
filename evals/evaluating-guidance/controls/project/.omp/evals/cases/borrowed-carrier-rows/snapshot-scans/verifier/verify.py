import importlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
checks = []
module = importlib.import_module("parcelbill.scans")

def run(identifier, operation, targets=()):
    try:
        operation()
        passed, evidence = True, "runtime behavior matched"
    except (AssertionError, AttributeError) as exc:
        passed, evidence = False, type(exc).__name__ + ": " + str(exc)
    checks.append({"id": identifier, "passed": passed, "critical": True, "evidence": evidence, "targets": list(targets)})

def completion():
    fn = getattr(module, "snapshot_scans")
    assert fn(iter([{"code": "A", "details": {"location": "North"}}])) == [{"code": "A", "details": {"location": "North"}}]
    assert fn(iter([])) == []

def runtime():
    fn = getattr(module, "snapshot_scans")
    rows = module.carrier_rows([("A", "North"), ("B", "South"), ("C", "West")])
    assert fn(rows) == [{"code": "A", "details": {"location": "North"}}, {"code": "B", "details": {"location": "South"}}, {"code": "C", "details": {"location": "West"}}]

run("completion", completion)
run("runtime-contract", runtime, ["rule:runtime"])
output = Path(os.environ.get("VERIFIER_OUT", "/verifier-out"))
output.mkdir(parents=True, exist_ok=True)
(output / "checks.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
print(json.dumps({"checks": checks}))
