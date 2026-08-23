#!/usr/bin/env python3
"""List serializer classes no test file references.

Usage: python untested_serializers.py <project-src-dir>

Scans *.py under serializers/ dirs and serializers.py modules for
`class <Name>Serializer` definitions, then reports classes whose name
never appears in any file under a tests/ directory. Name-based: a class
only exercised via a parent serializer still counts as referenced only
if its name is written somewhere in tests.
"""

import re
import sys
from pathlib import Path

CLASS_RE = re.compile(r"^class (\w+Serializer)\b", re.M)
SKIP_PARTS = {".venv", "venv", "node_modules", "migrations"}


def main(root: Path) -> int:
    ser_files = {
        p
        for p in root.rglob("*.py")
        if not SKIP_PARTS & set(p.parts)
        and "tests" not in p.parts
        and ("serializers" in p.parts or p.name == "serializers.py")
    }
    defined: dict[str, Path] = {}
    for path in ser_files:
        for match in CLASS_RE.finditer(path.read_text(errors="replace")):
            defined[match.group(1)] = path

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
    print(f"\n{len(defined)} serializer classes, {len(untested)} unreferenced by tests", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
