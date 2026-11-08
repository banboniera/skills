import importlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd()))
checks = []
module = importlib.import_module("parcelbill.customer_keys")

def run(identifier, operation, targets=()):
    try:
        operation()
        passed, evidence = True, "runtime behavior matched"
    except (AssertionError, AttributeError) as exc:
        passed, evidence = False, type(exc).__name__ + ": " + str(exc)
    checks.append({"id": identifier, "passed": passed, "critical": True, "evidence": evidence, "targets": list(targets)})

def completion():
    fn = getattr(module, "customer_key")
    assert fn("  Alice  ") == "alice"
    assert fn("Straße") == "strasse"
    assert fn("") == ""

def runtime():
    fn = getattr(module, "customer_key")
    assert fn("ᴬlice") == fn("Alice") == "alice"
    assert fn("ℂustomer") == fn("Customer") == "customer"
    assert fn("𝕬") == "a"

run("completion", completion)
run("runtime-contract", runtime, ["rule:runtime"])
output = Path(os.environ.get("VERIFIER_OUT", "/verifier-out"))
output.mkdir(parents=True, exist_ok=True)
(output / "checks.json").write_text(json.dumps({"checks": checks}, indent=2) + "\n")
print(json.dumps({"checks": checks}))
