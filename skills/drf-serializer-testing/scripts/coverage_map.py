#!/usr/bin/env python3
"""Print a test-coverage checklist for each serializer class in a file.

Usage: python coverage_map.py <serializers.py> [ClassName]

AST-based: lists what each serializer OWNS (declared fields, custom
validators, save overrides, representation hooks, context-driven
querysets) and maps each item to the test the coverage table demands.
Static heuristic — Meta-only ModelSerializer fields are not expanded;
read the model for those.
"""

import ast
import sys
from pathlib import Path

FIELD_HINTS = {
    "ChoiceField": "valid + invalid choice (error on field key)",
    "MultipleChoiceField": "valid set + invalid member",
    "PrimaryKeyRelatedField": "in-scope pk passes + out-of-scope pk fails at validation",
    "SlugRelatedField": "in-scope value passes + out-of-scope fails at validation",
    "SerializerMethodField": "output value matched against known fixture",
    "ListField": "valid list + empty/oversize boundary",
    "DecimalField": "precision boundary + coercion in validated_data",
    "IntegerField": "min/max boundary if configured",
    "CharField": "max_length/blank boundary if configured",
    "DateField": "format + boundary if configured",
    "DateTimeField": "format + boundary if configured",
}


def field_call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name and (name.endswith("Field") or name.endswith("Serializer")):
            return name
    return None


def kwarg_names(call: ast.Call) -> set[str]:
    return {kw.arg for kw in call.keywords if kw.arg}


def analyze(cls: ast.ClassDef, source: str) -> list[str]:
    items: list[str] = []
    warnings: list[str] = []
    for node in cls.body:
        if isinstance(node, ast.ClassDef) and node.name == "Meta":
            meta_seg = ast.get_source_segment(source, node) or ""
            if '"__all__"' in meta_seg or "'__all__'" in meta_seg:
                warnings.append('INCOMPLETE — Meta.fields = "__all__": model-derived fields not listed; read the model')
            elif "fields" in meta_seg or "exclude" in meta_seg:
                warnings.append("INCOMPLETE — Meta fields/exclude derive from model: only declared fields listed; read the model")
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            fname = field_call_name(node.value)
            if not fname:
                continue
            kwargs = kwarg_names(node.value)
            hint = FIELD_HINTS.get(fname, "owned field: valid + boundary/invalid value")
            if fname.endswith("Serializer"):
                hint = "nested: valid + invalid payload, errors surface on parent key"
            items.append(f"field {name} ({fname}): {hint}")
            if "write_only" in kwargs:
                items.append(f"field {name}: assert absent from .data (write_only)")
            if "queryset" in kwargs:
                items.append(f"field {name}: queryset scoping — in-scope passes, out-of-scope fails")
            if "default" in kwargs or "initial" in kwargs:
                items.append(f"field {name}: default applied when omitted")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
            if fn == "get_fields":
                warnings.append("INCOMPLETE — get_fields() override builds fields dynamically; read the method")
            seg = ast.get_source_segment(source, node) or ""
            if fn.startswith("validate_"):
                items.append(f"{fn}(): every branch — passing + each rejecting input, error key '{fn[9:]}'")
            elif fn == "validate":
                items.append("validate(): every branch — cross-field pass + each rejection, error key/shape")
            elif fn in ("create", "update"):
                items.append(f"{fn}(): persisted state + every side effect after save() (refresh_from_db)")
            elif fn == "to_representation":
                items.append("to_representation(): exact key set + transformed values vs fixtures")
            elif fn == "__init__" and "context" in seg:
                items.append("__init__ reads context: behavior per context value (user/company/language)")
            if "self.context" in seg and fn != "__init__":
                items.append(f"{fn}(): context-driven — set context, assert outcome")
    bases = ", ".join(ast.unparse(b) for b in cls.bases)
    if not items and not warnings:
        items.append("Meta-only serializer: exact .data key set + any configured extra_kwargs boundaries")
    header = [f"[{cls.name}({bases})]"] + [f"  ! {w}" for w in warnings]
    return header + [f"  - {i}" for i in items]


def main(path: Path, only: str | None) -> int:
    source = path.read_text(errors="replace")
    tree = ast.parse(source)
    found = False
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name != "Meta" and (only is None or node.name == only):
            if "Serializer" not in node.name and not any("Serializer" in ast.unparse(b) for b in node.bases):
                continue
            found = True
            print("\n".join(analyze(node, source)))
            print()
    if not found:
        print(f"no serializer classes{f' named {only}' if only else ''} in {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3) or not Path(sys.argv[1]).is_file():
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) == 3 else None))
