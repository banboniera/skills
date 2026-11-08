from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time
from typing import Any, cast
import uuid

from .arms import USER_ROOT, is_guidance, materialize
from .contracts import FREE_SMOKE_MODEL, Case, Checks, DiscoveredCase, Project, load_json, load_toml
from .dispatcher import Dispatcher
from .execution import admission_decision, effective_budget, extract_events, judge_checks, prompt_names_guidance, redact_artifacts
from .identity import IdentityInputs, admission_id, agent_hash, content_hash, directory_hash, engine_hash, grade_id, tree_hash
from .runner import GradeManifest, GradeResult, GradedCheck, TrialManifest, TrialResult, TrialSpec
from .sandbox import Sandbox, SeedInfo, parse_recorder_log
from .store import Store, atomic_write

FREE_MODEL = FREE_SMOKE_MODEL


@dataclass
class RunBudget:
    limit: float | None
    costs: dict[str, float] = field(default_factory=dict[str, float])
    uncertain_caps: set[str] = field(default_factory=set[str])
    running: float = 0.0

    def __post_init__(self) -> None:
        if self.limit is not None and (not math.isfinite(self.limit) or self.limit <= 0):
            raise ValueError("--budget must be a positive finite USD amount")

    @property
    def spent(self) -> float:
        return sum(self.costs.values())

    def record(self, trial_id: str, cost: float, uncertain: bool) -> None:
        self.costs[trial_id] = max(self.costs.get(trial_id, 0), cost)
        if uncertain:
            self.uncertain_caps.add(trial_id)

    def admit(self, cap: float) -> bool:
        if self.uncertain_caps:
            return False
        committed = self.spent + self.running + cap
        if self.limit is not None and committed > self.limit + 1e-12:
            return False
        self.running += cap
        return True

    def release(self, cap: float) -> None:
        self.running = max(0.0, self.running - cap)


@dataclass
class ExecutionSummary:
    scheduled_ids: list[str] = field(default_factory=list[str])
    infra_errors: dict[str, int] = field(default_factory=dict[str, int])
    stop_reason: str | None = None


def usage_spend(paths: list[Path]) -> tuple[float, bool]:
    """Count measured charges, including failed/interrupted attempts."""
    total = 0.0
    uncertain = False
    for path in paths:
        measured = 0.0
        final = 0.0
        missing = False
        for line in path.read_text().splitlines():
            raw: object = json.loads(line)
            if not isinstance(raw, dict):
                raise ValueError("invalid usage accounting record")
            record = cast(dict[str, object], raw)
            kind = record.get("type")
            if kind == "request" and record.get("measured") is not True:
                missing = True
                continue
            value = record.get("cost", 0)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid usage accounting cost")
            if kind == "request":
                measured += value
            elif kind == "revoked":
                final = float(value)
                count = record.get("unmeasured", 0)
                missing |= isinstance(count, (int, float)) and count > 0
        total += measured if missing else max(measured, final)
        uncertain |= missing
    return total, uncertain


def infrastructure_cause(error: str | None) -> str:
    message = error or "infrastructure failure"
    for prefix in ("RuntimeError: ", "ValueError: ", "SandboxError: "):
        message = message.removeprefix(prefix)
    return message


def jobs_default() -> int:
    return max(1, min(4, (os.cpu_count() or 2) // 4))


def guidance_files(root: Path) -> dict[str, bytes]:
    """Capture treatments; the evaluator's own user skill is never a treatment."""
    result: dict[str, bytes] = {}
    for directory, names, files in os.walk(root):
        names[:] = [n for n in names if n not in {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}]
        if Path(directory).name == ".omp" and "evals" in names:
            names.remove("evals")
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if is_guidance(relative) and not path.is_symlink():
                result[relative] = path.read_bytes()
    user = Path.home() / ".omp/agent"
    for filename in ["AGENTS.md", "RULES.md", "WATCHDOG.md", "CLAUDE.md"]:
        path = user / filename
        if path.is_file() and not path.is_symlink():
            result[USER_ROOT + filename] = path.read_bytes()
    for category in ["rules", "skills"]:
        for directory, names, files in os.walk(user / category):
            names[:] = [n for n in names if n not in {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}]
            if Path(directory) == user / "skills":
                names[:] = [name for name in names if name != "evaluating-guidance"]
            if Path(directory).name == ".omp" and "evals" in names:
                names.remove("evals")
            for name in files:
                path = Path(directory) / name
                if not path.is_symlink():
                    result[USER_ROOT + path.relative_to(user).as_posix()] = path.read_bytes()
    return result


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}).stdout


def capture_snapshot(root: Path, destination: Path) -> Path:
    """Independent clone plus tracked working changes, never mutates the source."""
    destination.mkdir(parents=True, exist_ok=True)
    snapshot = destination / uuid.uuid4().hex
    if not (root / ".git").exists():
        shutil.copytree(root, snapshot, symlinks=True,
                        ignore=shutil.ignore_patterns(".venv", "__pycache__", "node_modules"))
        _git(snapshot, "init", "--quiet")
        _git(snapshot, "add", "--all")
        _git(snapshot, "-c", "user.name=guidance-evals", "-c", "user.email=eval@localhost",
             "commit", "--quiet", "-m", "Private evaluation snapshot")
        return snapshot
    subprocess.run(["git", "clone", "--no-local", "--no-hardlinks", "--quiet", str(root), str(snapshot)], check=True)
    for remote in _git(snapshot, "remote").decode().splitlines():
        _git(snapshot, "remote", "remove", remote)
    patch = _git(root, "diff", "--binary", "--no-ext-diff", "--no-textconv", "HEAD", "--")
    if patch:
        subprocess.run(["git", "-C", str(snapshot), "apply", "--binary", "-"], input=patch, check=True)
    for raw in _git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0"):
        if not raw:
            continue
        relative = os.fsdecode(raw)
        source, target = root / relative, snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(source.readlink())
        else:
            shutil.copy2(source, target)
    return snapshot


class RealRunner:
    def __init__(self, project_root: Path, project: Project, store: Store, dispatcher: Dispatcher,
                 sandbox: Sandbox, seed: SeedInfo, guidance: dict[str, bytes],
                 blocks: dict[str, list[str]] | None = None, roles: dict[str, str] | None = None):
        self.project_root, self.project, self.store = project_root, project, store
        self.dispatcher, self.sandbox, self.seed = dispatcher, sandbox, seed
        self.guidance, self.blocks = guidance, blocks or project.blocks
        self.roles = roles or project.agent.roles
        self.references: dict[str, dict[str, bytes]] = {}

    def run_trial(self, trial: TrialSpec, *, readonly: bool = False) -> TrialResult:
        output = self.store.trial_path(trial.id)
        started = time.monotonic()
        output.mkdir(parents=True, exist_ok=True)
        if trial.case_dir is None:
            raise ValueError("real trial needs case_dir")
        case_dir = Path(trial.case_dir)
        case = load_toml(case_dir / "case.toml", Case)
        case = case.model_copy(update={"budget": effective_budget(case.budget, self.project.agent)})
        token = ""
        try:
            token = self.dispatcher.register(list(set(self.roles.values())), case.budget.max_cost,
                                             output / f"usage-{uuid.uuid4().hex}.jsonl")
            treatment = materialize(self.guidance, trial.arm, self.references.get(trial.arm), blocks=self.blocks)
            with self.sandbox.trial(self.seed, trial.id, case, case_dir, treatment) as environment:
                result = environment.run_agent(self.dispatcher.port, token, self.roles, output, readonly=readonly)
            if redact_artifacts(output, token):
                raise RuntimeError("agent copied a trial credential into the patch; patch redacted, grading refused")
            total = time.monotonic() - started
            (output / "timing.json").write_text(json.dumps({
                "agent_seconds": result.get("seconds", 0), "trial_seconds": total,
                "overhead_seconds": total - float(result.get("seconds", 0)), "phases": result.get("phases", {}),
                "agent_started_at": result.get("started_at")}) + "\n")
            events = extract_events(output / "events.jsonl")
            (output / "final_answer.txt").write_text(events["final_answer"])
            (output / "commands.json").write_text(json.dumps(events["commands"], indent=2) + "\n")
            outcome = TrialResult(status="complete", seconds=result["seconds"])
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
            error = infrastructure_cause(f"{type(exc).__name__}: {exc}")
            if token:
                error = error.replace(token, "[REDACTED_TRIAL_TOKEN]")
            (output / "infra-error.txt").write_text(error + "\n")
            outcome = TrialResult(status="infra_error", error=error)
        finally:
            if token:
                redact_artifacts(output, token)
                usage = self.dispatcher.revoke(token)
            else:
                usage = {"cost": 0, "tokens": 0}
        unmeasured = usage.get("unmeasured", 0)
        uncertain = isinstance(unmeasured, (int, float)) and unmeasured > 0
        artifacts = {p.relative_to(output).as_posix(): p.relative_to(output).as_posix()
                     for p in output.rglob("*") if p.is_file() and not p.is_symlink() and p.name != "manifest.json"}
        return TrialResult.model_validate({**outcome.model_dump(), "artifacts": artifacts,
            "cost": None if uncertain else usage.get("cost", 0), "tokens": usage.get("tokens", 0),
            "budget_overshoot": usage.get("overshoot", 0), "accounting_unknown": uncertain})

    def grade(self, trial: TrialManifest) -> GradeResult:
        if trial.result.status != "complete":
            return GradeResult(status="infra_error", error="trial did not complete")
        if trial.spec.case_dir is None:
            raise ValueError("real grade needs case_dir")
        case_dir = Path(trial.spec.case_dir)
        case = load_toml(case_dir / "case.toml", Case)
        output = self.store.trial_path(trial.spec.id)
        verifier, judge = self.grade_inputs(trial.spec)
        grading = self.store.root / "grades" / grade_id(trial.spec.id, verifier, judge) / "artifacts"
        grading.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        try:
            checks = self.sandbox.verify(self.seed, case, case_dir, output / "diff.patch", grading)
            verifier_seconds = time.monotonic() - started
            graded = [GradedCheck(**c.model_dump(), source="verifier") for c in checks.checks]
            recorder = output / "recorder.jsonl"
            attempts = parse_recorder_log(recorder.read_text())
            graded.append(GradedCheck(id="external-effects",
                passed=attempts["valid"] is True and attempts["denied"] == 0, source="safety",
                evidence=f"recorder valid={attempts['valid']}; denied={attempts['denied']}"))
            evidence = {"diff": (output / "diff.patch").read_text(),
                        "final_answer": (output / "final_answer.txt").read_text(),
                        "commands": (output / "commands.json").read_text(),
                        "verifier_log": (grading / "verifier.log").read_text(),
                        "transcript": (output / "events.jsonl").read_text()[-100_000:]}
            judge_started = time.monotonic()
            graded.extend(judge_checks(case_dir, self.project.judge, evidence, self.dispatcher, grading))
            atomic_write(grading / "grading-timing.json", (json.dumps({
                "verifier_seconds": verifier_seconds,
                "judge_seconds": time.monotonic() - judge_started,
                "grade_seconds": time.monotonic() - started}) + "\n").encode())
            return GradeResult(checks=graded, artifacts={
                path.name: path.relative_to(self.store.root).as_posix()
                for path in grading.iterdir() if path.is_file()})
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
            return GradeResult(status="infra_error", error=f"{type(exc).__name__}: {exc}")

    def grade_inputs(self, spec: TrialSpec) -> tuple[str, str]:
        case_dir = Path(spec.case_dir or "")
        verifier = directory_hash(case_dir / "verifier")
        judge = content_hash({"settings": self.project.judge.model_dump(by_alias=True),
            "questions": (case_dir / "judge.toml").read_text() if (case_dir / "judge.toml").exists() else ""})
        return verifier, judge

    def grade_trial(self, spec: TrialSpec) -> bool:
        """Grade saved artifacts only; never start or repair an agent trial."""
        if self.store.needs_trial(spec.id):
            return False
        verifier, judge = self.grade_inputs(spec)
        if not self.store.needs_grade(spec.id, verifier, judge):
            return False
        self.store.save_grade(spec.id, verifier, judge, self.grade(self.store.load_trial(spec.id)))
        return True

    def trial_cap(self, spec: TrialSpec) -> float:
        case = load_toml(Path(spec.case_dir or "") / "case.toml", Case)
        return effective_budget(case.budget, self.project.agent).max_cost

    def account_trials(self, specs: list[TrialSpec], budget: RunBudget) -> None:
        unique = dict.fromkeys(spec.id for spec in specs)
        grade_usage: dict[str, list[Path]] = {ident: [] for ident in unique}
        for path in (self.store.root / "grades").glob("*/manifest.json"):
            grade = load_json(path, GradeManifest)
            if grade.trial_id in unique:
                grade_usage[grade.trial_id].extend((path.parent / "artifacts").glob("judge-usage-*.jsonl"))
        for ident in unique:
            directory = self.store.trial_path(ident)
            agent_paths = list(directory.glob("usage-*.jsonl"))
            cost, uncertain = usage_spend([*agent_paths, *grade_usage[ident]])
            manifest = directory / "manifest.json"
            if manifest.exists():
                result = self.store.load_trial(ident).result
                if not agent_paths:
                    cost += result.cost or 0.0
                uncertain |= result.accounting_unknown
            budget.record(ident, cost, uncertain)

    def trial_infrastructure_error(self, spec: TrialSpec) -> str | None:
        result = self.store.load_trial(spec.id).result
        if result.status == "infra_error":
            return infrastructure_cause(result.error)
        verifier, judge = self.grade_inputs(spec)
        path = self.store.root / "grades" / grade_id(spec.id, verifier, judge) / "manifest.json"
        if path.exists():
            grade = load_json(path, GradeManifest).result
            if grade.status == "infra_error":
                return infrastructure_cause(grade.error)
        return None

    def execute(self, specs: list[TrialSpec], jobs: int, *, budget: RunBudget | None = None) -> ExecutionSummary:
        if jobs < 1:
            raise ValueError("jobs must be positive")
        ledger = budget if budget is not None else RunBudget(None)
        unique = list({spec.id: spec for spec in specs}.values())
        summary = ExecutionSummary()
        self.account_trials(unique, ledger)
        for spec in unique:
            if not self.store.needs_trial(spec.id):
                if ledger.limit is not None and ledger.spent >= ledger.limit:
                    summary.stop_reason = "budget"
                    return summary
                self.grade_trial(spec)
        self.account_trials(unique, ledger)
        pending = [spec for spec in unique if self.store.needs_trial(spec.id)]
        first_wave = True
        offset = 0
        pool = ThreadPoolExecutor(max_workers=jobs)
        try:
            while offset < len(pending):
                wave: list[tuple[TrialSpec, float]] = []
                while offset < len(pending) and len(wave) < jobs:
                    spec = pending[offset]
                    cap = self.trial_cap(spec)
                    if not ledger.admit(cap):
                        break
                    wave.append((spec, cap))
                    summary.scheduled_ids.append(spec.id)
                    offset += 1
                if not wave:
                    summary.stop_reason = "budget"
                    break
                def one(spec: TrialSpec) -> None:
                    self.store.save_trial(spec, self.run_trial(spec))
                    self.grade_trial(spec)
                try:
                    list(pool.map(one, [spec for spec, _ in wave]))
                finally:
                    for _, cap in wave:
                        ledger.release(cap)
                    self.account_trials(unique, ledger)
                causes = [cause for spec, _ in wave if (cause := self.trial_infrastructure_error(spec)) is not None]
                counts = Counter(summary.infra_errors)
                counts.update(causes)
                summary.infra_errors = dict(counts)
                if first_wave and len(causes) == len(wave) and len(set(causes)) == 1:
                    summary.stop_reason = "first-wave-infra"
                    break
                first_wave = False
        except BaseException:
            self.sandbox.cancel()
            raise
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        return summary


def admit_cases(runner: RealRunner, cases: list[DiscoveredCase], selectors: list[str], *,
                jobs: int | None = None) -> list[dict[str, Any]]:
    workers = jobs_default() if jobs is None else jobs
    if workers < 1:
        raise ValueError("jobs must be positive")
    selected = [case for case in cases if not selectors
                or any(fnmatchcase(case.key, s) or fnmatchcase(case.spec.id, s) for s in selectors)]
    if not selected:
        return []
    for case in selected:
        if prompt_names_guidance(case.spec.prompt, case.spec.targets):
            raise ValueError(f"{case.key}: prompt names guidance")
    selected_by_key = {case.key: case for case in selected}
    for previous in (runner.store.root / "admissions").glob("*/admission.json"):
        admitted: dict[str, Any] = json.loads(previous.read_text())
        key = admitted.get("case")
        if (admitted.get("admission_id") and admitted.get("admitted") is True
                and isinstance(key, str) and key in selected_by_key
                and admitted.get("case_hash") != selected_by_key[key].case_hash):
            raise ValueError(f"{key}: admitted execution inputs are frozen; use a new case ID")
    execution_agent = agent_hash(runner.project, runner.seed.image, runner.roles)
    prepared: list[tuple[DiscoveredCase, str, str, str]] = []
    for case in selected:
        reference = case.path / "reference.patch"
        if not reference.is_file():
            raise ValueError(f"{case.key}: missing reference.patch")
        verifier = directory_hash(case.path / "verifier")
        reference_hash = content_hash(reference.read_bytes().hex())
        admission = admission_id(case.case_hash, verifier, reference_hash, execution_agent)
        prepared.append((case, verifier, reference_hash, admission))

    def one(case: DiscoveredCase, verifier: str, reference_hash: str, admission: str) -> dict[str, Any]:
        output = runner.store.root / "admissions" / admission
        output.mkdir(parents=True, exist_ok=True)
        reference = case.path / "reference.patch"
        empty = output / "base.patch"
        empty.write_text("")
        refs: list[Checks] = []
        bases: list[Checks] = []
        record: dict[str, Any] = {"case": case.key, "case_hash": case.case_hash,
            "snapshot": runner.seed.snapshot_hash, "image": runner.seed.image, "agent_hash": execution_agent,
            "verifier_hash": verifier, "reference_hash": reference_hash, "admission_id": admission, "admitted": False}
        try:
            for index in range(2):
                refs.append(runner.sandbox.verify(runner.seed, case.spec, case.path, reference, output / f"reference-{index}"))
                bases.append(runner.sandbox.verify(runner.seed, case.spec, case.path, empty, output / f"base-{index}"))
            record["admitted"], record["reason"] = admission_decision(refs, bases)
            record["reference"] = [r.model_dump() for r in refs]
            record["base"] = [b.model_dump() for b in bases]
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
            record.update(status="infra_error", reason=f"{type(exc).__name__}: {exc}")
        atomic_write(output / "admission.json", (json.dumps(record, indent=2) + "\n").encode())
        return record

    pool = ThreadPoolExecutor(max_workers=workers)
    main_thread = threading.current_thread() is threading.main_thread()
    previous = signal.getsignal(signal.SIGTERM)
    try:
        if main_thread:
            def terminate(signum: int, _frame: object) -> None:
                raise SystemExit(128 + signum)
            signal.signal(signal.SIGTERM, terminate)
        futures = {pool.submit(one, *inputs): index for index, inputs in enumerate(prepared)}
        results: dict[int, dict[str, Any]] = {}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
        return [results[index] for index in range(len(prepared))]
    except BaseException:
        runner.sandbox.cancel()
        raise
    finally:
        try:
            pool.shutdown(wait=True, cancel_futures=True)
        finally:
            if main_thread:
                signal.signal(signal.SIGTERM, previous)


def make_spec(seed_hash: str, guidance: dict[str, bytes], agent: dict[str, Any], case: DiscoveredCase,
              arm: str = "current", replicate: int = 0) -> TrialSpec:
    return TrialSpec(identity=IdentityInputs(snapshot=seed_hash, arm=tree_hash(materialize(guidance, arm)),
        case=case.case_hash, agent=content_hash(agent), engine=engine_hash(), replicate=replicate),
        arm=arm, case_key=case.key, family=case.family, targets=case.spec.targets, case_dir=str(case.path))
