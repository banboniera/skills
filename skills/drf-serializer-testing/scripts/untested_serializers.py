#!/usr/bin/env python3
"""List DRF serializer classes no test file mentions.

Usage: python untested_serializers.py <project-src-dir>

Finds classes whose name or a base class name ends in `Serializer`, in any
non-test module, then reports the ones whose name appears in no .py file under
a tests/ directory or named test_*.py. Name matching only: a serializer tested
only through a parent that nests it, or a base class tested through its
subclasses, shows up too, so judge the list.
"""

import ast
import re
import sys
from pathlib import Path

SKIP_PARTS = {".venv", "venv", "node_modules", "migrations", "site-packages"}


def looks_like_serializer(cls: ast.ClassDef) -> bool:
    names = [cls.name] + [ast.unparse(base).split(".")[-1] for base in cls.bases]
    return any(name.endswith("Serializer") for name in names)


def is_test(path: Path) -> bool:
    return "tests" in path.parts or path.name.startswith("test_")


def main(root: Path) -> int:
    sources = [p for p in root.rglob("*.py") if not SKIP_PARTS & set(p.parts)]
    defined: dict[str, Path] = {}
    for path in sources:
        if is_test(path):
            continue
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and looks_like_serializer(node):
                defined[node.name] = path

    test_text = "\n".join(p.read_text(errors="replace") for p in sources if is_test(p))
    untested = sorted(
        (str(path.relative_to(root)), name)
        for name, path in defined.items()
        if not re.search(rf"\b{re.escape(name)}\b", test_text)
    )
    for path, name in untested:
        print(f"{path}: {name}")
    print(f"\n{len(defined)} serializer classes, {len(untested)} not mentioned by any test", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
