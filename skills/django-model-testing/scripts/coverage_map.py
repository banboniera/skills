#!/usr/bin/env python3
"""Print a test-coverage checklist for each model class in a file.

Usage: python coverage_map.py <models.py> [ClassName]

AST-based: lists what each model OWNS (validators, clean, save/delete
overrides, Meta.constraints, properties with logic, on_commit usage,
custom managers) and maps each item to the test the coverage table
demands. Static heuristic — inherited behavior from abstract bases is
reported on the base, not repeated per subclass; run on the base's file
too.
"""

import ast
import sys
from pathlib import Path


def kwarg_names(call: ast.Call) -> set[str]:
    return {kw.arg for kw in call.keywords if kw.arg}


def analyze(cls: ast.ClassDef, source: str) -> list[str]:
    items: list[str] = []
    for node in cls.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if not isinstance(node.value, ast.Call):
                continue
            seg = ast.unparse(node.value)
            kwargs = kwarg_names(node.value)
            if "validators" in kwargs:
                items.append(f"field {name}: validator boundary — full_clean() pass at edge + fail pinned to '{name}' via message_dict")
            if "unique" in kwargs:
                items.append(f"field {name}: uniqueness — pre-create conflict, assert at enforcing layer")
            if "Manager" in seg or name == "objects" and "(" in seg and "models.Manager()" not in seg:
                items.append(f"manager {name}: inclusion AND exclusion (rows that must not appear)")
        elif isinstance(node, ast.ClassDef) and node.name == "Meta":
            meta_seg = ast.get_source_segment(source, node) or ""
            if "constraints" in meta_seg:
                items.append("Meta.constraints: each constraint at its enforcing layer(s); DB-layer failure inside nested atomic; read names from Meta, never guess")
            if "unique_together" in meta_seg:
                items.append("Meta.unique_together: pre-create conflict, assert ValidationError via full_clean or IntegrityError in nested atomic")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
            seg = ast.get_source_segment(source, node) or ""
            decorators = {ast.unparse(d) for d in node.decorator_list}
            if fn == "clean":
                items.append("clean(): every branch — passing + each rejection pinned to field via message_dict; note save() never calls it")
            elif fn == "save":
                items.append("save(): mutation asserted on STORED row after reload; each derived/normalized field")
                if "update_fields" in seg:
                    items.append("save(): update_fields path — partial save omitting the touched field still persists override behavior")
            elif fn == "delete":
                items.append("delete(): instance path + queryset path (QuerySet.delete() skips this override); soft-delete: flag + date + manager visibility")
            elif any("property" in d for d in decorators):
                body_stmts = [s for s in node.body if not isinstance(s, (ast.Expr,))]  # ignore docstring
                has_logic = any(isinstance(s, (ast.If, ast.For, ast.Try)) for s in ast.walk(node))
                if has_logic or len(body_stmts) > 1:
                    items.append(f"property {fn}: branching read contract — test each branch/boundary")
            if "on_commit" in seg:
                items.append(f"{fn}(): on_commit side effect — prove with captureOnCommitCallbacks()")
    bases = ", ".join(ast.unparse(b) for b in cls.bases)
    if "abstract = True" in (ast.get_source_segment(source, cls) or ""):
        items.append("abstract base: test through cheap concrete subclass")
    if not items:
        items.append("no owned behavior found statically — check inherited bases, signals registered elsewhere, and skip if truly plain")
    return [f"[{cls.name}({bases})]"] + [f"  - {i}" for i in items]


def looks_like_model(cls: ast.ClassDef) -> bool:
    bases = " ".join(ast.unparse(b) for b in cls.bases)
    return "models." in bases or "Model" in bases


def main(path: Path, only: str | None) -> int:
    source = path.read_text(errors="replace")
    tree = ast.parse(source)
    found = False
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name != "Meta" and (only is None or node.name == only):
            if not looks_like_model(node):
                continue
            found = True
            print("\n".join(analyze(node, source)))
            print()
    if not found:
        print(f"no model classes{f' named {only}' if only else ''} in {path}", file=sys.stderr)
        return 1
    print("! NOT VISIBLE STATICALLY — signal receivers registered outside this file (signals.py/apps.py)"
          " and behavior inherited from bases in other files; grep receivers + run on base files. Reading the code stays authoritative.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3) or not Path(sys.argv[1]).is_file():
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) == 3 else None))
