"""Strict file boundaries. Errors identify the file and field, never input values."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
import tomllib
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Name = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
Duration = Annotated[str, Field(pattern=r"^[1-9][0-9]*(?:s|m|h)$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or "\x00" in value:
        raise ValueError("expected a safe relative POSIX path")
    if str(path) != value or value == ".":
        raise ValueError("expected a normalized nonempty path")
    return value


def validate_target(value: str) -> str:
    if value in {"all", "user-all"}:
        return value
    kind, sep, name = value.partition(":")
    if not sep or kind not in {"rule", "skill", "file", "user-rule", "user-skill", "user-file"}:
        raise ValueError("unknown guidance target syntax")
    if kind.endswith("file"):
        relative_path(name)
    elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("expected a rule or skill name")
    return value


class Image(StrictModel):
    containerfile: str
    context: str = "."


class Seed(StrictModel):
    warm: list[str] = Field(default_factory=list)
    cache_dirs: list[str] = Field(default_factory=list)


class Service(StrictModel):
    image: str
    env: dict[str, str] = Field(default_factory=dict)
    init: str | None = None
    ready: str
    args: list[str] = Field(default_factory=list)


class Budget(StrictModel):
    max_time: Duration = "25m"
    max_cost: float = Field(default=6.0, gt=0, allow_inf_nan=False)


class Agent(Budget):
    roles: dict[str, str]


class JudgeSettings(StrictModel):
    model: str = "openrouter/~typesafe/jev-latest"
    second: str | None = None
    pass_threshold: float = Field(default=0.8, alias="pass", ge=0, le=1)
    fail: float = Field(default=0.2, ge=0, le=1)

    @model_validator(mode="after")
    def thresholds(self) -> Self:
        if self.fail >= self.pass_threshold:
            raise ValueError("fail must be below pass")
        return self

FREE_SMOKE_MODEL = "openrouter/nvidia/nemotron-3.5-lightning:free"


def is_free_model(model: str) -> bool:
    return model.endswith(":free") or model.startswith("local/")


class Project(StrictModel):
    slug: Name
    holdout: int = Field(default=30, ge=0, le=50)
    workdir: str = "/work/repo"
    image: Image
    hide: list[str] = Field(default_factory=lambda: [".omp/evals", ".env*", ".envrc"])
    results: str = "~/.cache/guidance-evals"
    seed: Seed = Field(default_factory=Seed)
    services: dict[str, Service] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    agent: Agent
    judge: JudgeSettings = Field(default_factory=JudgeSettings)
    protected: list[str] = Field(default_factory=list)
    blocks: dict[Name, list[str]] = Field(default_factory=dict)
    # Model for smoke and --free runs; free or local only, so its results stay smoke-only.
    smoke_model: str = FREE_SMOKE_MODEL

    @field_validator("smoke_model")
    @classmethod
    def smoke_model_free(cls, value: str) -> str:
        if not is_free_model(value):
            raise ValueError("smoke_model must be a free (`:free`) or local (`local/`) model")
        return value

    @field_validator("blocks")
    @classmethod
    def blocks_valid(cls, values: dict[str, list[str]]) -> dict[str, list[str]]:
        for targets in values.values():
            if not targets or len(set(targets)) != len(targets):
                raise ValueError("blocks require nonempty unique targets")
            for target in targets:
                validate_target(target)
        return values

    @field_validator("protected")
    @classmethod
    def targets_valid(cls, values: list[str]) -> list[str]:
        return [validate_target(v) for v in values]

    @field_validator("workdir")
    @classmethod
    def absolute_workdir(cls, value: str) -> str:
        path = PurePosixPath(value)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("workdir must be an absolute POSIX path")
        return value


class Case(StrictModel):
    id: Name
    family: Name | None = None
    targets: list[str] = Field(min_length=1)
    services: list[str] = Field(default_factory=list)
    prompt: str = Field(min_length=1)
    seed: Literal["project", "files"] = "project"
    budget: Budget = Field(default_factory=Budget)

    @field_validator("targets")
    @classmethod
    def targets_valid(cls, values: list[str]) -> list[str]:
        return [validate_target(v) for v in values]


class Check(StrictModel):
    id: Name
    passed: bool
    critical: bool = True
    evidence: str = ""
    targets: list[str] = Field(default_factory=list[str])

    @field_validator("targets")
    @classmethod
    def targets_valid(cls, values: list[str]) -> list[str]:
        return [validate_target(v) for v in values]


class Checks(StrictModel):
    checks: list[Check] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_checks(self) -> Self:
        if len({c.id for c in self.checks}) != len(self.checks):
            raise ValueError("duplicate check id")
        if not any(c.id == "completion" and c.critical for c in self.checks):
            raise ValueError("checks must include critical completion")
        return self


Evidence = Literal["final_answer", "diff", "commands", "verifier_log", "transcript"]


class Question(StrictModel):
    id: Name
    critical: bool = True
    evidence: list[Evidence] = Field(min_length=1)
    text: str = Field(min_length=1)
    targets: list[str] = Field(default_factory=list[str])

    @field_validator("targets")
    @classmethod
    def targets_valid(cls, values: list[str]) -> list[str]:
        return [validate_target(v) for v in values]


class Judge(StrictModel):
    question: list[Question] = Field(default_factory=list[Question])

    @model_validator(mode="after")
    def unique_questions(self) -> Self:
        if len({q.id for q in self.question}) != len(self.question):
            raise ValueError("duplicate question id")
        return self


class Trigger(StrictModel):
    skill: Name
    should: list[str] = Field(min_length=1)
    should_not: list[str] = Field(min_length=1)
    window: int = Field(default=6, gt=0)


class ContractError(ValueError):
    """A malformed input file, including its path and failing field."""


def _validation_error(path: Path, exc: ValidationError) -> ContractError:
    details = "; ".join(f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['type']}"
                        for err in exc.errors(include_input=False, include_context=False))
    return ContractError(f"{path}: {details}")


def load_toml[T: BaseModel](path: Path, model: type[T]) -> T:
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        return model.model_validate(data)
    except ValidationError as exc:
        raise _validation_error(path, exc) from None
    except (OSError, tomllib.TOMLDecodeError):
        raise ContractError(f"{path}: <root>: cannot read valid TOML") from None


def load_json[T: BaseModel](path: Path, model: type[T]) -> T:
    try:
        return model.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise _validation_error(path, exc) from None
    except OSError:
        raise ContractError(f"{path}: <root>: cannot read valid JSON") from None


class DiscoveredCase(StrictModel):
    spec: Case
    family: str
    path: Path
    case_hash: str

    @property
    def key(self) -> str:
        return f"{self.family}/{self.spec.id}"


def discover_cases(project_root: Path, project: Project) -> list[DiscoveredCase]:
    from .identity import case_execution_hash

    result: list[DiscoveredCase] = []
    seen: set[str] = set()
    for path in sorted((project_root / ".omp/evals/cases").glob("*/*/case.toml")):
        case = load_toml(path, Case)
        family = path.parent.parent.name
        if case.family is not None and case.family != family:
            raise ContractError(f"{path}: family: must match directory")
        if case.id in seen:
            raise ContractError(f"{path}: id: duplicate case id")
        seen.add(case.id)
        if set(case.services) - project.services.keys():
            raise ContractError(f"{path}: services: unknown project service")
        if case.seed == "files" and not (path.parent / "seed").is_dir():
            raise ContractError(f"{path}: seed: files requires seed directory")
        judge = path.parent / "judge.toml"
        if judge.exists():
            load_toml(judge, Judge)
        result.append(DiscoveredCase(spec=case, family=family, path=path.parent,
                                     case_hash=case_execution_hash(case, path.parent)))
    return result
