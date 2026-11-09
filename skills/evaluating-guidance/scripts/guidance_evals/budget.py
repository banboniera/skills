"""Host-side spend accounting for paid runs.

Kept out of the execution identity (`identity.EXECUTION_SOURCES`): accounting decides
whether to start a trial, never what a trial's agent sees or does.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import cast

from .contracts import load_json
from .runner import GradeManifest
from .store import Store


@dataclass
class RunBudget:
    limit: float | None
    costs: dict[str, float] = field(default_factory=dict[str, float])
    unbounded: set[str] = field(default_factory=set[str])
    running: float = 0.0

    def __post_init__(self) -> None:
        if self.limit is not None and (not math.isfinite(self.limit) or self.limit <= 0):
            raise ValueError("--budget must be a positive finite USD amount")

    @property
    def spent(self) -> float:
        return sum(self.costs.values())

    def record(self, trial_id: str, cost: float, unbounded: bool) -> None:
        self.costs[trial_id] = max(self.costs.get(trial_id, 0), cost)
        if unbounded:
            self.unbounded.add(trial_id)

    def admit(self, cap: float) -> bool:
        # Spend with no known upper bound could already exceed the budget.
        if self.unbounded:
            return False
        committed = self.spent + self.running + cap
        if self.limit is not None and committed > self.limit + 1e-12:
            return False
        self.running += cap
        return True

    def release(self, cap: float) -> None:
        self.running = max(0.0, self.running - cap)


def _amount(value: object, what: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"invalid usage accounting {what}")
    return float(value)


def usage_spend(paths: list[Path]) -> tuple[float, bool]:
    """Return an upper bound on charges, including failed and interrupted attempts.

    A request interrupted before its cost was measured counts at the ceiling the
    dispatcher recorded for it. The flag is true when some request has no ceiling,
    so the true spend is unbounded.
    """
    total = 0.0
    unbounded = False
    for path in paths:
        measured = 0.0
        final = 0.0
        unmeasured = 0
        reported_unmeasured = 0.0
        for line in path.read_text().splitlines():
            raw: object = json.loads(line)
            if not isinstance(raw, dict):
                raise ValueError("invalid usage accounting record")
            record = cast(dict[str, object], raw)
            kind = record.get("type")
            if kind == "request" and record.get("measured") is not True:
                unmeasured += 1
                ceiling = record.get("costCeiling")
                if ceiling is None:
                    unbounded = True
                else:
                    measured += _amount(ceiling, "ceiling")
            elif kind == "request":
                measured += _amount(record.get("cost", 0), "cost")
            elif kind == "revoked":
                final = _amount(record.get("cost", 0), "cost")
                reported_unmeasured = _amount(record.get("unmeasured", 0), "unmeasured count")
        # An unmeasured request without its own record has no recorded ceiling.
        unbounded |= reported_unmeasured > unmeasured
        # The dispatcher's final total excludes unmeasured requests, so it only stands
        # in for the request records when every request was measured.
        total += measured if unmeasured else max(measured, final)
    return total, unbounded


def account_trials(store: Store, trial_ids: Iterable[str], budget: RunBudget) -> None:
    """Record every listed trial's agent and judge spend, from usage files when present."""
    unique = dict.fromkeys(trial_ids)
    grade_usage: dict[str, list[Path]] = {ident: [] for ident in unique}
    for path in (store.root / "grades").glob("*/manifest.json"):
        grade = load_json(path, GradeManifest)
        if grade.trial_id in unique:
            grade_usage[grade.trial_id].extend((path.parent / "artifacts").glob("judge-usage-*.jsonl"))
    for ident in unique:
        directory = store.trial_path(ident)
        agent_paths = list(directory.glob("usage-*.jsonl"))
        cost, unbounded = usage_spend([*agent_paths, *grade_usage[ident]])
        if not agent_paths and (directory / "manifest.json").exists():
            # Without a usage file the saved result is the only record of agent spend.
            result = store.load_trial(ident).result
            cost += result.cost or 0.0
            unbounded |= result.accounting_unknown
        budget.record(ident, cost, unbounded)
