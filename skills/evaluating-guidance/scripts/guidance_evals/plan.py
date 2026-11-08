"""Layered group testing, sealed holdouts and balanced fixed-look scheduling.

expand_experiments resolves whole/blocks/split/holdout into two-arm comparisons;
pass its returned block map to arms.materialize. advance_look advances an entire
unresolved comparison from k=3 to k=6, never individual cases. plan_trials returns
the complete frozen plan; trial ids already in the store are reused, so shared
current trials and earlier replicates are not rerun. Materialized arm CONTENT (not
labels) determines trial identity.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
import hashlib
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator
from typing import Self

from .contracts import DiscoveredCase, Name, StrictModel, validate_target
from .identity import IdentityInputs
from .runner import TrialSpec


class Experiment(StrictModel):
    name: Name
    kind: Literal["whole", "blocks", "split", "holdout", "compare"] = "compare"
    arms: list[str] = Field(default_factory=lambda: ["current", "none"], min_length=2, max_length=2)
    selectors: list[str] = Field(default_factory=lambda: ["*"])
    relevant_targets: list[str] = Field(default_factory=list[str])
    replicates: int = Field(default=3, gt=0)
    looks: list[int] = Field(default_factory=lambda: [3, 6])
    split: Literal["behavior", "holdout"] = "behavior"
    holdout: int = Field(default=30, ge=0, le=50)
    block: str | None = None
    ref: str | None = None
    split_mode: Literal["halves", "members"] = "halves"

    @field_validator("arms")
    @classmethod
    def arms_valid(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("duplicate arm")
        for value in values:
            if value in {"current", "none"} or (value.startswith("ref:") and len(value) > 4):
                continue
            if value.startswith("minus:"):
                target = value[6:]
                if ":" in target or target in {"all", "user-all"}:
                    validate_target(target)
                elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", target):
                    raise ValueError("invalid block name")
            else:
                raise ValueError("invalid arm")
        return values

    @model_validator(mode="after")
    def valid_looks(self) -> Self:
        if self.looks not in ([3, 6], [3], [1]) or self.replicates not in self.looks:
            raise ValueError("supported looks are [3,6], [3], or smoke-only [1]")
        return self


class ExpandedPlan(StrictModel):
    comparisons: list[Experiment]
    blocks: dict[str, list[str]]

def removed_targets(arm: str, blocks: dict[str, list[str]]) -> list[str]:
    """Named targets removed by one arm; common removals are not a contrast."""
    if not arm.startswith("minus:"):
        return []
    target = arm.removeprefix("minus:")
    return list(blocks[target]) if target in blocks else [validate_target(target)]



def expand_experiments(experiment: Experiment, blocks: dict[str, list[str]]) -> ExpandedPlan:
    """Expand strategy; split halves use deterministic block--part-N names."""
    groups = {name: list(members) for name, members in blocks.items()}
    comparisons: list[Experiment] = []

    def comparison(name: str, arms: list[str], members: list[str], split: str = "behavior") -> Experiment:
        data = experiment.model_dump()
        data.update(name=name, kind="compare", arms=arms, relevant_targets=members, split=split)
        return Experiment.model_validate(data)

    if experiment.kind == "whole":
        comparisons = [comparison(experiment.name, ["current", "none"], [])]
    elif experiment.kind == "blocks":
        for block, members in groups.items():
            comparisons.append(comparison(f"{experiment.name}--{block}", ["current", f"minus:{block}"], members))
    elif experiment.kind == "split":
        if experiment.block not in groups:
            raise ValueError("split requires a configured block")
        members = groups[experiment.block]
        if len(members) < 2:
            raise ValueError("cannot split a single-member block")
        if experiment.split_mode == "members":
            partitions = [[member] for member in members]
        else:
            midpoint = (len(members)+1)//2
            partitions = [members[:midpoint], members[midpoint:]]
        for index, partition in enumerate(partitions):
            block = f"{experiment.block}--part-{index+1}"
            if block in groups:
                raise ValueError("generated split block collides with a configured block")
            groups[block] = partition
            comparisons.append(comparison(f"{experiment.name}--part-{index+1}", ["current", f"minus:{block}"], partition))
    elif experiment.kind == "holdout":
        if not experiment.ref:
            raise ValueError("holdout requires ref revision")
        comparisons = [comparison(experiment.name, ["current", f"ref:{experiment.ref}"], [], "holdout")]
    else:
        first, second = (removed_targets(arm, groups) for arm in experiment.arms)
        members = list(dict.fromkeys(experiment.relevant_targets))
        if not members:
            members = [target for target in dict.fromkeys([*first, *second])
                       if (target in first) != (target in second)]
        comparisons = [comparison(experiment.name, experiment.arms, members, experiment.split)]
    if not comparisons:
        raise ValueError("strategy has no configured blocks")
    return ExpandedPlan(comparisons=comparisons, blocks=groups)


def advance_look(experiment: Experiment, verdict: str) -> Experiment | None:
    """Only an unresolved comparison may schedule the next ALL-case balanced look."""
    if verdict != "inconclusive" or experiment.replicates == 6:
        return None
    return experiment.model_copy(update={"replicates": 6})


def is_holdout(family: str, percent: int) -> bool:
    if not 0 <= percent <= 50:
        raise ValueError("holdout percent must be between 0 and 50")
    return int.from_bytes(hashlib.sha256(family.encode()).digest(), "big") % 100 < percent


def select_cases(experiment: Experiment, cases: list[DiscoveredCase]) -> list[DiscoveredCase]:
    relevant_targets = set(experiment.relevant_targets)
    return [case for case in sorted(cases, key=lambda c: c.key)
            if is_holdout(case.family, experiment.holdout) == (experiment.split == "holdout")
            and (not relevant_targets or not relevant_targets.isdisjoint(case.spec.targets))
            and any(fnmatchcase(value, pattern) for pattern in experiment.selectors
                    for value in [case.key, case.family, *case.spec.targets])]


def plan_trials(experiment: Experiment, cases: list[DiscoveredCase], *, snapshot: str,
                arm_hashes: dict[str, str], agent_hash: str, engine_hash: str) -> list[TrialSpec]:
    missing = set(experiment.arms) - arm_hashes.keys()
    if missing:
        raise ValueError("arm_hashes must resolve every experiment arm")
    result: list[TrialSpec] = []
    for case in select_cases(experiment, cases):
        offset = int.from_bytes(hashlib.sha256(case.key.encode()).digest()[:4], "big")
        for replicate in range(experiment.replicates):
            order = experiment.arms[::-1] if (offset + replicate) % 2 else experiment.arms
            for arm in order:
                inputs = IdentityInputs(snapshot=snapshot, arm=arm_hashes[arm], case=case.case_hash,
                                        agent=agent_hash, engine=engine_hash, replicate=replicate)
                result.append(TrialSpec(identity=inputs, arm=arm, case_key=case.key, family=case.family,
                                        targets=case.spec.targets, case_dir=str(case.path)))
    return result
