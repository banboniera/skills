import importlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
checks = []
module = importlib.import_module("parcelbill.transit")

def run(identifier, operation, targets=()):
    try:
        operation()
        passed, evidence = True, "runtime behavior matched"
    except (AssertionError, AttributeError) as exc:
        passed, evidence = False, type(exc).__name__ + ": " + str(exc)
    checks.append({"id": identifier, "passed": passed, "critical": True, "evidence": evidence, "targets": list(targets)})

def completion():
    fn = getattr(module, "elapsed_seconds")
    from datetime import datetime, timezone
    assert fn(datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, 1, tzinfo=timezone.utc)) == 3600

def runtime():
    fn = getattr(module, "elapsed_seconds")
    from datetime import datetime
    zone = module.carrier_zone()
    start = datetime(2025, 10, 26, 2, 30, tzinfo=zone, fold=0)
    end = datetime(2025, 10, 26, 2, 30, tzinfo=zone, fold=1)
    assert fn(start, end) == 3600
    assert fn(end, start) == -3600
    assert fn(datetime(2025, 3, 30, 1, 30, tzinfo=zone), datetime(2025, 3, 30, 3, 30, tzinfo=zone)) == 3600

run("completion", completion)
run("runtime-contract", runtime, ["rule:runtime"])
output = Path(os.environ.get("VERIFIER_OUT", "/verifier-out"))
output.mkdir(parents=True, exist_ok=True)
(output / "checks.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
print(json.dumps({"checks": checks}))
