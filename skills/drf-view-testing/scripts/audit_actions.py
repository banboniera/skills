#!/usr/bin/env python3
"""Cross-check DRF view actions against a test module.

Usage: audit_actions.py <views.py> [test_module.py] [--shared <mixins.py>]...

Lists every action each ViewSet exposes (router defaults, own @action methods,
and @action methods inherited from classes defined in --shared files), and —
when a test module is given — which actions the tests never reference.
Pass the project's shared view/mixin modules via --shared so inherited actions
(by-pks, restore, confirm, ...) are resolved; bases not defined in any given
file stay unresolved and are printed for manual checking.
"""

import ast
import re
import sys

ROUTER_ACTIONS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]
READONLY_ACTIONS = ["list", "retrieve"]


def base_name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def class_map(tree: ast.Module) -> dict:
    """All classes in a module: name -> (bases, own @action method names)."""
    out = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        actions = [
            m.name
            for m in cls.body
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(base_name(getattr(d, "func", d)) == "action" for d in m.decorator_list)
        ]
        out[cls.name] = ([base_name(b) for b in cls.bases], actions)
    return out


def resolve(name: str, classes: dict, seen=None) -> tuple:
    """Transitive (actions, unresolved_bases) over classes defined in given files."""
    seen = seen or set()
    if name in seen or name not in classes:
        return [], [name] if name not in classes else []
    seen.add(name)
    bases, actions = classes[name]
    actions = list(actions)
    unresolved = []
    for b in bases:
        a, u = resolve(b, classes, seen)
        actions += a
        unresolved += u
    return actions, unresolved


def main() -> int:
    args = sys.argv[1:]
    shared_files = []
    while "--shared" in args:
        i = args.index("--shared")
        shared_files.append(args[i + 1])
        del args[i : i + 2]
    if not args:
        print(__doc__.strip())
        return 2

    shared_classes = {}
    for f in shared_files:
        shared_classes.update(class_map(ast.parse(open(f).read())))
    view_tree = ast.parse(open(args[0]).read())
    view_classes = class_map(view_tree)
    classes = {**shared_classes, **view_classes}
    # resolve "import X as Y" aliases against the shared definitions
    for node in ast.walk(view_tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.asname and a.name in shared_classes:
                    classes[a.asname] = shared_classes[a.name]
    test_src = open(args[1]).read() if len(args) > 1 else None

    missing_total = []
    for name, (bases, _) in view_classes.items():
        if not any(b.endswith(("ViewSet", "View", "Mixin")) for b in bases):
            continue
        inherited, unresolved = resolve(name, classes)
        chain = " ".join([name] + bases + unresolved)
        if "ReadOnly" in chain:
            defaults = list(READONLY_ACTIONS)
        elif re.search(r"\w+ViewSet\b(?<!GenericViewSet)", " ".join(bases + unresolved)):
            # LIMITATION: custom *ViewSet bases assumed ModelViewSet-like; GenericViewSet-only combos over-report.
            defaults = list(ROUTER_ACTIONS)
        else:
            defaults = []
        actions = list(dict.fromkeys(defaults + inherited))
        print(f"{name} (bases: {', '.join(bases)})")
        if unresolved:
            print(f"  [unresolved bases, check by hand: {', '.join(dict.fromkeys(unresolved))}]")
        for a in actions:
            if test_src is None:
                print(f"  {a}")
                continue
            # referenced via as_view({...: "a"}), reverse("...-a"), url path, or test names
            hit = re.search(rf'["\']{a}["\']|[-_/]{a.replace("_", "[-_]")}\b', test_src)
            mark = "tested" if hit else "MISSING"
            print(f"  {a:<20} {mark}")
            if not hit:
                missing_total.append(f"{name}.{a}")
    if test_src is not None:
        print(f"\n{len(missing_total)} untested action(s)" + (": " + ", ".join(missing_total) if missing_total else ""))
    return 1 if missing_total else 0


if __name__ == "__main__":
    sys.exit(main())
