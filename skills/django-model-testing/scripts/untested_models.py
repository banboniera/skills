#!/usr/bin/env python3
"""List Django model classes no test file references.

Usage: python untested_models.py <project-src-dir>

Scans models.py modules and models/ packages for class definitions whose
base list looks like a model (contains `models.` or a name ending in
`Model`), then reports classes whose name never appears in any file under
a tests/ directory. Name-based heuristic: abstract bases and models only
exercised through subclasses may be false positives — judge the output.
"""

import re
import sys
from pathlib import Path

CLASS_RE = re.compile(r"^class (\w+)\(([^)]*)\)\s*:", re.M)
BASE_RE = re.compile(r"(?:\bmodels\.\w+|\w*Model\b)")
SKIP_PARTS = {".venv", "venv", "node_modules", "migrations"}


def main(root: Path) -> int:
    model_files = {
        p
        for p in root.rglob("*.py")
        if not SKIP_PARTS & set(p.parts)
        and "tests" not in p.parts
        and (p.name == "models.py" or "models" in p.parts)
    }
    defined: dict[str, Path] = {}
    for path in model_files:
        for match in CLASS_RE.finditer(path.read_text(errors="replace")):
            name, bases = match.groups()
            if name != "Meta" and BASE_RE.search(bases):
                defined[name] = path

    test_text = "".join(
        p.read_text(errors="replace")
        for p in root.rglob("tests/**/*.py")
        if not SKIP_PARTS & set(p.parts)
    )

    untested = sorted(
        (str(path.relative_to(root)), name)
        for name, path in defined.items()
        if name not in test_text
    )
    for path, name in untested:
        print(f"{path}: {name}")
    print(f"\n{len(defined)} model classes, {len(untested)} unreferenced by tests", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
