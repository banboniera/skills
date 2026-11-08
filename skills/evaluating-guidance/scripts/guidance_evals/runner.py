"""Runner boundary: execute, then grade immutable artifacts; no sandbox backend.

Artifact values are paths relative to the trial directory. A backend writes those
files before returning. Infrastructure failures use infra_error, not failed
completion. Agent failures are complete trials with a false completion check.
"""
from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .contracts import StrictModel, relative_path, validate_target
from .identity import IdentityInputs


class GradedCheck(StrictModel):
    id: str
    passed: bool | None
    critical: bool = True
    source: Literal["verifier", "safety", "judge"] = "verifier"
    evidence: str = ""
    targets: list[str] = Field(default_factory=list[str])
    # Judged questions only: whether the second judge decided differently.
    disagreement: bool | None = None

    @field_validator("targets")
    @classmethod
    def targets_valid(cls, values: list[str]) -> list[str]:
        return [validate_target(v) for v in values]


class TrialSpec(StrictModel):
    identity: IdentityInputs
    arm: str
    case_key: str
    family: str
    targets: list[str]
    case_dir: str | None = None
    snapshot_path: str | None = None
    guidance_path: str | None = None
    agent_config_path: str | None = None

    @property
    def id(self) -> str:
        return self.identity.trial_id


class TrialResult(StrictModel):
    status: Literal["complete", "infra_error"]
    artifacts: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    tokens: int | None = Field(default=None, ge=0)
    seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    exposed: bool | None = Field(default=None, exclude=True)
    budget_overshoot: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    accounting_unknown: bool = False

    @field_validator("artifacts")
    @classmethod
    def artifact_paths(cls, values: dict[str, str]) -> dict[str, str]:
        for path in values.values():
            relative_path(path)
        return values


class TrialManifest(StrictModel):
    spec: TrialSpec
    result: TrialResult


class GradeResult(StrictModel):
    status: Literal["complete", "infra_error"] = "complete"
    checks: list[GradedCheck] = Field(default_factory=list[GradedCheck])
    error: str | None = None
    confirmed_critical_counterexample: bool = False

    artifacts: dict[str, str] = Field(default_factory=dict)

    @field_validator("artifacts")
    @classmethod
    def artifact_paths(cls, values: dict[str, str]) -> dict[str, str]:
        for path in values.values():
            relative_path(path)
        return values

    @model_validator(mode="after")
    def unique_checks(self) -> Self:
        keys = [(c.source, c.id) for c in self.checks]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate check source/id")
        return self


class GradeManifest(StrictModel):
    trial_id: str
    verifier_hash: str
    judge_hash: str
    engine_hash: str = ""
    result: GradeResult


class Observation(StrictModel):
    trial_id: str
    case_key: str
    family: str
    arm: str
    replicate: int
    checks: list[GradedCheck] = Field(default_factory=list[GradedCheck])
    infra_error: bool = False
    cost: float | None = None
    tokens: int | None = None
    seconds: float | None = None
    exposed: bool | None = None
    confirmed_critical_counterexample: bool = False
    targets: list[str] = Field(default_factory=list[str])


class FakeRunner:
    """Deterministic positive-effect control, never executes tools or models."""

    def run_trial(self, trial: TrialSpec) -> TrialResult:
        return TrialResult(status="complete", cost=0.01, tokens=100, seconds=0.1)

    def grade(self, trial: TrialManifest) -> GradeResult:
        return GradeResult(checks=[GradedCheck(id="completion", passed=True),
                                  GradedCheck(id="control", passed=trial.spec.arm == "current"),
                                  GradedCheck(id="external-effects", passed=True, source="safety")])
