"""Atomic manifests are commit markers; uncommitted/infra trials are retried.

No mutable latest-grade pointer: callers choose a verifier/judge identity when
multiple complete grades exist, preventing accidental rubric mixing.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile

from pydantic import BaseModel

from .contracts import ContractError, load_json
from .exposure import artifact_exposure
from .identity import grading_engine_hash, grade_id
from .runner import GradeManifest, GradeResult, Observation, TrialManifest, TrialResult, TrialSpec


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_model(path: Path, value: BaseModel) -> None:
    atomic_write(path, (value.model_dump_json(indent=2) + "\n").encode())


def _id(value: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("expected a SHA-256 identity")
    return value


class Store:
    def __init__(self, root: Path):
        self.root = root.expanduser()

    @classmethod
    def for_project(cls, slug: str, results: str = "~/.cache/guidance-evals") -> Store:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", slug):
            raise ValueError("invalid project slug")
        return cls(Path(results).expanduser() / slug)

    def trial_path(self, trial_id: str) -> Path:
        return self.root / "trials" / _id(trial_id)

    def load_trial(self, trial_id: str) -> TrialManifest:
        manifest = load_json(self.trial_path(trial_id) / "manifest.json", TrialManifest)
        if manifest.spec.id != trial_id:
            raise ContractError(f"{self.trial_path(trial_id)}: identity: manifest mismatch")
        return manifest

    def needs_trial(self, trial_id: str) -> bool:
        try:
            manifest = self.load_trial(trial_id)
        except ContractError:
            return True
        return manifest.result.status != "complete" or any(
            not (self.trial_path(trial_id) / p).is_file() for p in manifest.result.artifacts.values())

    def save_trial(self, spec: TrialSpec, result: TrialResult) -> None:
        atomic_model(self.trial_path(spec.id) / "manifest.json", TrialManifest(spec=spec, result=result))

    def save_grade(self, trial_id: str, verifier_hash: str, judge_hash: str, result: GradeResult) -> str:
        self.load_trial(trial_id)
        engine = grading_engine_hash()
        ident = grade_id(trial_id, verifier_hash, judge_hash, engine)
        atomic_model(self.root / "grades" / ident / "manifest.json",
                     GradeManifest(trial_id=trial_id, verifier_hash=verifier_hash, judge_hash=judge_hash,
                                   engine_hash=engine, result=result))
        return ident

    def needs_grade(self, trial_id: str, verifier_hash: str, judge_hash: str) -> bool:
        ident = grade_id(trial_id, verifier_hash, judge_hash)
        try:
            grade = load_json(self.root / "grades" / ident / "manifest.json", GradeManifest)
        except ContractError:
            return True
        return grade.result.status != "complete"

    def observations(self, *, specs: list[TrialSpec] | None = None,
                     verifier_hash: str | None = None, judge_hash: str | None = None,
                     engine_hash: str | None = None,
                     exposure_targets: list[str] | None = None,
                     grading_versions: dict[str, tuple[str | None, str | None, str | None]] | None = None) -> list[Observation]:
        """Select per-trial verifier/judge/engine versions, falling back to uniform filters."""
        default_versions = (verifier_hash, judge_hash, engine_hash)
        selected_ids = {spec.id for spec in specs} if specs is not None else None
        grades: dict[str, list[GradeManifest]] = {}
        for path in sorted((self.root / "grades").glob("*/manifest.json")):
            grade = load_json(path, GradeManifest)
            if path.parent.name != grade_id(grade.trial_id, grade.verifier_hash, grade.judge_hash, grade.engine_hash):
                raise ContractError(f"{path}: identity: grade mismatch")
            if selected_ids is not None and grade.trial_id not in selected_ids:
                continue
            verifier, judge, engine = (grading_versions.get(grade.trial_id, default_versions)
                                       if grading_versions is not None else default_versions)
            if engine is not None and grade.engine_hash != engine:
                continue
            if verifier is not None and grade.verifier_hash != verifier:
                continue
            if judge is not None and grade.judge_hash != judge:
                continue
            grades.setdefault(grade.trial_id, []).append(grade)
        if specs is None:
            specs = [load_json(path, TrialManifest).spec for path in sorted((self.root / "trials").glob("*/manifest.json"))]
        result: list[Observation] = []
        for spec in specs:
            try:
                trial = self.load_trial(spec.id)
            except ContractError:
                result.append(Observation(trial_id=spec.id, case_key=spec.case_key, family=spec.family,
                    arm=spec.arm, replicate=spec.identity.replicate, targets=spec.targets, infra_error=True))
                continue
            candidates = [g for g in grades.get(spec.id, []) if g.result.status == "complete"]
            if len(candidates) > 1:
                raise ValueError("multiple grades: select verifier_hash, judge_hash and engine_hash explicitly")
            grade = candidates[0].result if candidates else None
            trial_path = self.trial_path(spec.id)
            incomplete_trial = trial.result.status != "complete" or any(
                not (trial_path / path).is_file() for path in trial.result.artifacts.values())
            result.append(Observation(trial_id=spec.id, case_key=spec.case_key, family=spec.family,
                arm=spec.arm, replicate=spec.identity.replicate, checks=grade.checks if grade else [],
                targets=spec.targets,
                infra_error=incomplete_trial or grade is None,
                cost=trial.result.cost, tokens=trial.result.tokens, seconds=trial.result.seconds,
                exposed=artifact_exposure(trial_path, trial.result.artifacts, exposure_targets or []),
                confirmed_critical_counterexample=grade.confirmed_critical_counterexample if grade else False))
        return result
