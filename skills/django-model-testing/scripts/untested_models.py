#!/usr/bin/env python3
"""List Django model classes no test file mentions.

Usage: python untested_models.py <project-src-dir>

Finds classes in models.py modules and models/ packages whose bases look like
models (a `models.` attribute or a name ending in `Model`), then reports the
ones whose name appears in no .py file under a tests/ directory or named
test_*.py. Name matching only: an abstract base shows up even when its
subclasses are tested, so judge the list.
"""

import ast
import re
import sys
from pathlib import Path

SKIP_PARTS = {".venv", "venv", "node_modules", "migrations", "site-packages"}


def looks_like_model(cls: ast.ClassDef) -> bool:
    for base in cls.bases:
        text = ast.unparse(base)
        if text.startswith("models.") or text.split(".")[-1].endswith("Model"):
            return True
    return False


def is_test(path: Path) -> bool:
    return "tests" in path.parts or path.name.startswith("test_")


def main(root: Path) -> int:
    sources = [p for p in root.rglob("*.py") if not SKIP_PARTS & set(p.parts)]
    defined: dict[str, Path] = {}
    for path in sources:
        if is_test(path) or not (path.name == "models.py" or "models" in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and looks_like_model(node):
                defined[node.name] = path

    test_text = "\n".join(p.read_text(errors="replace") for p in sources if is_test(p))
    untested = sorted(
        (str(path.relative_to(root)), name)
        for name, path in defined.items()
        if not re.search(rf"\b{re.escape(name)}\b", test_text)
    )
    for path, name in untested:
        print(f"{path}: {name}")
    print(f"\n{len(defined)} model classes, {len(untested)} not mentioned by any test", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_dir():
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
