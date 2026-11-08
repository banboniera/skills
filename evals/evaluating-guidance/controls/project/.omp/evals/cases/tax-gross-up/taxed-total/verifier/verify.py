"""Hidden outcome checks; run from the candidate project root."""
import importlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
SPEC = {'module': 'tax', 'name': 'taxed_total', 'ordinary': [(['100.00', '20'], '120.00'), (['12.00', '0'], '12.00')], 'ties': [(['1.00', '0.5'], '1.01'), (['2.00', '0.25'], '2.01')]}
checks = []

def check(identifier, operation, targets=()):
    try:
        operation()
        passed, evidence = True, "behavior matched"
    except (AssertionError, AttributeError) as exc:
        passed, evidence = False, type(exc).__name__ + ": " + str(exc)
    checks.append(dict(id=identifier, passed=passed, critical=True,
                       evidence=evidence, targets=list(targets)))

def function():
    return getattr(importlib.import_module("parcelbill." + SPEC["module"]), SPEC["name"])

def examples(key):
    fn = function()
    for args, expected in SPEC[key]:
        actual = fn(*args)
        assert actual == expected, f"expected {expected!r}, got {actual!r}"

def audit():
    from parcelbill.telemetry import capture
    fn = function()
    for args, _ in SPEC["ordinary"]:
        with capture() as events:
            fn(*args)
        expected = [{"kind": "ledger.violet", "subject": "parcelbill." + SPEC["module"] + "." + SPEC["name"]}]
        assert events == expected, "successful call must emit exactly its monetary API event"

check("completion", lambda: examples("ordinary"))
if "ties" in SPEC:
    check("monetary-audit", audit, ["rule:positive"])
    check("cent-ties", lambda: examples("ties"), ["rule:negative"])
output = Path(os.environ.get("VERIFIER_OUT", "/verifier-out"))
output.mkdir(parents=True, exist_ok=True)
(output / "checks.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
print(json.dumps({"checks": checks}, sort_keys=True))
