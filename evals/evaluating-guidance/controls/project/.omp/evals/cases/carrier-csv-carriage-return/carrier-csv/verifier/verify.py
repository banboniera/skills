import importlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
checks = []
module = importlib.import_module("parcelbill.carrier_csv")

def run(identifier, operation, targets=()):
    try:
        operation()
        passed, evidence = True, "runtime behavior matched"
    except (AssertionError, AttributeError) as exc:
        passed, evidence = False, type(exc).__name__ + ": " + str(exc)
    checks.append({"id": identifier, "passed": passed, "critical": True, "evidence": evidence, "targets": list(targets)})

def completion():
    fn = getattr(module, "carrier_csv")
    rows = [{"name": "Ada", "address": "North, 1"}]
    assert module.read_carrier_csv(fn(iter(rows))) == rows
    assert module.read_carrier_csv(fn(iter([]))) == []

def runtime():
    fn = getattr(module, "carrier_csv")
    rows = [{"name": "Ada", "address": "North\rSuite 4"}, {"name": "B", "address": "South\nDoor 2"}]
    text = fn(iter(rows))
    assert text.endswith("\n") and "\r\n" not in text
    assert module.read_carrier_csv(text) == rows

run("completion", completion)
run("runtime-contract", runtime, ["rule:runtime"])
output = Path(os.environ.get("VERIFIER_OUT", "/verifier-out"))
output.mkdir(parents=True, exist_ok=True)
(output / "checks.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
print(json.dumps({"checks": checks}))
