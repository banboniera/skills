from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from .contracts import Project, discover_cases
from .identity import admission_id, agent_hash, content_hash, directory_hash
from .sandbox import Sandbox
from .store import Store


def admission_status(root: Path, project: Project, store: Store) -> dict[str, object]:
    """Count unique valid cases and explain stale records without executing work.

    Stale entries contain the case key, storage directory id, and short reasons.
    A missing local image makes every saved admission unverifiable.
    """
    cases = {case.key: case for case in discover_cases(root, project)}
    image = Sandbox(root, project, store.root, "status").status_image()
    execution_agent = agent_hash(project, image, project.agent.roles) if image is not None else None
    current: dict[str, dict[str, str]] = {}
    unavailable: dict[str, list[str]] = {}
    for key, case in cases.items():
        hashes = {"case_hash": case.case_hash}
        reasons: list[str] = []
        verifier = case.path / "verifier"
        reference = case.path / "reference.patch"
        if verifier.is_dir():
            hashes["verifier_hash"] = directory_hash(verifier)
        else:
            reasons.append("verifier missing")
        if reference.is_file():
            hashes["reference_hash"] = content_hash(reference.read_bytes().hex())
        else:
            reasons.append("reference missing")
        if image is None or execution_agent is None:
            reasons.append("current image unavailable")
        else:
            hashes.update(image=image, agent_hash=execution_agent)
        if not reasons:
            hashes["admission_id"] = admission_id(hashes["case_hash"], hashes["verifier_hash"],
                                                   hashes["reference_hash"], hashes["agent_hash"])
        current[key], unavailable[key] = hashes, reasons

    admitted: set[str] = set()
    stale: list[dict[str, object]] = []
    labels = {"case_hash": "case changed", "verifier_hash": "verifier changed",
              "reference_hash": "reference changed", "agent_hash": "agent changed", "image": "image changed"}
    for path in sorted((store.root / "admissions").glob("*/admission.json")):
        try:
            data: object = json.loads(path.read_bytes())
        except (OSError, ValueError):
            data = None
        if not isinstance(data, dict):
            stale.append({"case": None, "id": path.parent.name, "reasons": ["invalid admission record"]})
            continue
        record = cast(dict[str, object], data)
        if record.get("admitted") is not True:
            continue
        key = record.get("case")
        if not isinstance(key, str) or key not in cases:
            reasons = ["case missing"]
        elif not record.get("admission_id"):
            reasons = ["missing admission identity"]
        else:
            hashes = current[key]
            reasons = [*unavailable[key], *(label for field, label in labels.items()
                                             if field in hashes and record.get(field) != hashes[field])]
            if not reasons and record.get("admission_id") != hashes.get("admission_id"):
                reasons.append("admission identity mismatch")
            if not reasons and path.parent.name != hashes.get("admission_id"):
                reasons.append("admission storage identity mismatch")
            if not reasons:
                admitted.add(key)
        if reasons:
            stale.append({"case": key if isinstance(key, str) else None,
                          "id": path.parent.name, "reasons": reasons})
    return {"admitted": len(admitted), "stale_admissions": stale}
