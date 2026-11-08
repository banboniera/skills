from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from typing import Any, Generator
import uuid

from .admission_status import admission_status
from .arms import materialize
from .cli import FrozenPlan, plan_path
from .contracts import Budget, Case, DiscoveredCase, Project, Trigger, discover_cases, is_free_model, load_json, load_toml
from .dispatcher import Dispatcher, reap_dispatchers
from .execution import extract_events, skill_loaded
from .identity import admission_id, agent_hash, content_hash, directory_hash, engine_hash, grading_engine_hash, tree_hash
from .plan import Experiment, expand_experiments, plan_trials
from .runtime import RealRunner, RunBudget, admit_cases, capture_snapshot, guidance_files, jobs_default, make_spec
from .sandbox import Sandbox, hidden_from_seed, janitor, seed_patterns
from .runner import TrialSpec
from .store import Store, atomic_model, atomic_write

SHORT_TRIAL_COST = 0.05


def untracked_in_seed(root: Path, project: Project) -> list[str] | None:
    """Untracked files the agent will see; authoring material here can leak answers."""
    if not (root / ".git").exists():
        return None
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"],
                            capture_output=True, check=True).stdout
    patterns = seed_patterns(project.hide, [p for p in project.seed.cache_dirs if not p.startswith("/")])
    return sorted(path for path in (os.fsdecode(raw) for raw in listed.split(b"\0") if raw)
                  if not hidden_from_seed(path, patterns))


@contextmanager
def prepared(root: Path, project: Project, db: Store, *, free: bool = False) -> Generator[RealRunner]:
    run_id = uuid.uuid4().hex
    run_root = db.root / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    snapshot = capture_snapshot(root, db.root / "snapshots")
    try:
        guidance = guidance_files(snapshot)
        sandbox = Sandbox(root, project, db.root, run_id)
        seed = sandbox.prepare(snapshot)
        with Dispatcher(run_root / "dispatcher") as dispatcher:
            roles = {name: project.smoke_model for name in project.agent.roles} if free else project.agent.roles
            yield RealRunner(root, project, db, dispatcher, sandbox, seed, guidance, roles=roles)
    finally:
        shutil.rmtree(snapshot)


def _temporary_case(directory: Path, prompt: str, *, max_time: str = "5m",
                    max_cost: float = SHORT_TRIAL_COST) -> DiscoveredCase:
    directory.mkdir(parents=True, exist_ok=True)
    spec = Case(id="smoke", family="smoke", targets=["all"], prompt=prompt,
                budget=Budget(max_time=max_time, max_cost=max_cost))
    # TOML string syntax equals JSON string syntax for these simple values.
    (directory / "case.toml").write_text(f'id="smoke"\nfamily="smoke"\ntargets=["all"]\nprompt={json.dumps(prompt)}\n'
        f'[budget]\nmax_time="{max_time}"\nmax_cost={max_cost}\n')
    return DiscoveredCase(spec=spec, family="smoke", path=directory, case_hash=directory_hash(directory))


def _smoke(runner: RealRunner, prompt: str, budget: float | None) -> dict[str, Any]:
    # Free by default; with a user-approved budget the one trial uses the production roles.
    case = _temporary_case(runner.store.root / "smoke-case", prompt,
                           max_cost=budget if budget is not None else SHORT_TRIAL_COST)
    spec = make_spec(runner.seed.snapshot_hash, runner.guidance,
                     {"image": runner.seed.image, "roles": runner.roles, "smoke": True}, case)
    reused = not runner.store.needs_trial(spec.id)
    if not reused:
        runner.store.save_trial(spec, runner.run_trial(spec))
    result = runner.store.load_trial(spec.id).result
    if result.status != "complete":
        limited = "429" in str(result.error) or "rate limit" in str(result.error).lower()
        hint = (" The free smoke model is rate-limited; retry later, set another free `smoke_model` in "
                "project.toml, or ask the user for a small budget and pass --budget USD." if limited and budget is None else "")
        raise RuntimeError(f"smoke infrastructure failed: {result.error}.{hint}")
    output = runner.store.trial_path(spec.id)
    diff = output / "diff.patch"
    if not diff.exists() or not diff.stat().st_size:
        raise RuntimeError("smoke agent produced no diff")
    return {"trial": spec.id, "status": result.status, "cost": result.cost, "seconds": result.seconds,
            "reused": reused, "artifacts": str(output), "isolation": json.loads((output / "isolation.json").read_text())}


def update_grading_versions(runner: RealRunner, frozen: FrozenPlan) -> None:
    versions = {spec.id: runner.grade_inputs(spec) for spec in frozen.trials}
    frozen.grading_verifiers = {ident: version[0] for ident, version in versions.items()}
    frozen.grading_judges = {ident: version[1] for ident, version in versions.items()}
    engine = grading_engine_hash()
    frozen.grading_engines = {spec.id: engine for spec in frozen.trials}


def regrade_plan(root: Path, db: Store, frozen: FrozenPlan) -> int:
    """Refresh grades from saved trials; source/image/execution config must match."""
    root = root.resolve()
    project = load_toml(root / ".omp/evals/project.toml", Project)
    with prepared(root, project, db) as runner:
        runner.roles = frozen.agent_roles or project.agent.roles
        execution = agent_hash(project, runner.seed.image, runner.roles)
        if any(spec.identity.snapshot != runner.seed.snapshot_hash or spec.identity.agent != execution
               for spec in frozen.trials):
            raise ValueError("regrading requires the original source, image and execution configuration")
        count = sum(runner.grade_trial(spec) for spec in {s.id: s for s in frozen.trials}.values())
        update_grading_versions(runner, frozen)
        return count


def run_experiment(runner: RealRunner, path: Path, jobs: int, *, budget: float | None = None) -> dict[str, Any]:
    if jobs < 1:
        raise ValueError("jobs must be positive")
    paid = not all(is_free_model(model) for model in runner.roles.values())
    if budget is None and paid:
        raise ValueError("Ask the user for a run budget; pass it as --budget USD")
    ledger = RunBudget(budget)
    planned: list[tuple[FrozenPlan, Path]] = []
    strategy = load_toml(path, Experiment).model_copy(update={"holdout": runner.project.holdout})
    if strategy.looks == [1] and paid:
        raise ValueError("k=1 requires free/local smoke models")
    cases = discover_cases(runner.project_root, runner.project)
    expanded = expand_experiments(strategy, runner.project.blocks)
    runner.blocks = expanded.blocks
    scheduled: set[str] = set()
    for experiment in expanded.comparisons:
        arm_hashes: dict[str, str] = {}
        for arm in experiment.arms:
            ref = None
            if arm.startswith("ref:"):
                with tempfile.TemporaryDirectory(prefix="guidance-ref-") as temporary:
                    reference = Path(temporary) / "repo"
                    subprocess.run(["git", "clone", "--no-local", "--no-hardlinks", "--quiet", str(runner.project_root), str(reference)], check=True)
                    subprocess.run(["git", "-C", str(reference), "-c", "core.hooksPath=/dev/null", "checkout", "--quiet", "--detach", arm[4:]], check=True)
                    ref = guidance_files(reference)
                runner.references[arm] = ref
            arm_hashes[arm] = tree_hash(materialize(runner.guidance, arm, ref, blocks=expanded.blocks))
        specs = plan_trials(experiment, cases, snapshot=runner.seed.snapshot_hash, arm_hashes=arm_hashes,
            agent_hash=agent_hash(runner.project, runner.seed.image, runner.roles), engine_hash=engine_hash())
        if not specs:
            raise ValueError("no cases match experiment selectors/split")
        selected = {s.case_key for s in specs}
        unadmitted: list[str] = []
        readmit: list[str] = []
        for case in cases:
            if case.key in selected:
                admission_key = admission_id(case.case_hash, directory_hash(case.path / "verifier"),
                    content_hash((case.path / "reference.patch").read_bytes().hex()),
                    agent_hash(runner.project, runner.seed.image, runner.roles))
                record = runner.store.root / "admissions" / admission_key / "admission.json"
                admission: dict[str, Any] = json.loads(record.read_text()) if record.exists() else {}
                if admission.get("admitted") is not True:
                    unadmitted.append(case.key)
                elif admission.get("snapshot") != runner.seed.snapshot_hash or admission.get("image") != runner.seed.image:
                    readmit.append(case.key)
        # Name every blocked case at once so one admission call can fix them all.
        if unadmitted or readmit:
            problems = ([f"run admit before experiments: {' '.join(unadmitted)}"] if unadmitted else []) + (
                [f"re-admit for this snapshot/image: {' '.join(readmit)}"] if readmit else [])
            raise ValueError("; ".join(problems))
        frozen = FrozenPlan(experiment=experiment, trials=specs, protected=runner.project.protected, blocks=expanded.blocks,
            smoke_only=any(is_free_model(model) for model in runner.roles.values()),
            agent_roles=runner.roles)
        plan_path_value = plan_path(runner.store, experiment.name)
        if plan_path_value.exists():
            previous = load_json(plan_path_value, FrozenPlan)
            same_inputs = previous.experiment == frozen.experiment and [s.id for s in previous.trials] == [s.id for s in specs]
            extended = (previous.experiment.replicates == 3 and experiment.replicates == 6
                and previous.experiment == experiment.model_copy(update={"replicates": 3})
                and {s.id for s in previous.trials}.issubset({s.id for s in specs}))
            if not same_inputs and not extended:
                raise ValueError("experiment name frozen with different inputs; choose a new name")
        atomic_model(plan_path_value, frozen)
        planned.append((frozen, plan_path_value))
    all_specs = [spec for frozen, _ in planned for spec in frozen.trials]
    runner.account_trials(all_specs, ledger)
    causes: Counter[str] = Counter()
    stop_reason: str | None = None
    for frozen, path_value in planned:
        execution = runner.execute(frozen.trials, jobs, budget=ledger)
        scheduled.update(execution.scheduled_ids)
        causes.update(execution.infra_errors)
        update_grading_versions(runner, frozen)
        atomic_model(path_value, frozen)
        if execution.stop_reason is not None:
            stop_reason = execution.stop_reason
            break
    completed = {spec.id for spec in all_specs if not runner.store.needs_trial(spec.id)}
    error_count = sum(causes.values())
    description = "; ".join(f"{count} × {cause}" for cause, count in sorted(causes.items()))
    return {"store": str(runner.store.root), "comparisons": [frozen.experiment.name for frozen, _ in planned],
            "scheduled_trials": len(scheduled), "complete_trials": len(completed),
            "spent": ledger.spent, "budget": ledger.limit,
            "budget_overshoot": max(0.0, ledger.spent - ledger.limit) if ledger.limit is not None else 0.0,
            "unmeasured_trials": len(ledger.uncertain_caps), "stop_reason": stop_reason,
            "infra_errors": dict(causes), "infra_error_count": error_count,
            "summary": f"{error_count} infra errors: {description}" if causes else "no infrastructure errors"}


def measure_triggers(runner: RealRunner, skill: str, budget: float | None) -> dict[str, Any]:
    path = runner.project_root / ".omp/evals/triggers" / f"{skill}.toml"
    trigger = load_toml(path, Trigger)
    if trigger.skill != skill:
        raise ValueError("trigger skill does not match filename")
    paid = not all(is_free_model(model) for model in runner.roles.values())
    if paid and budget is None:
        raise ValueError("Ask the user for a run budget; pass it as --budget USD (or use --free)")
    # Same cumulative ledger as `run`: admit only while measured spend plus running caps fit the
    # budget, stop on unknown usage; in-flight requests can still overshoot by one request.
    ledger = RunBudget(budget)
    specs: list[TrialSpec] = []
    results: list[dict[str, Any]] = []
    stop_reason: str | None = None
    prompts = [(True, index, prompt) for index, prompt in enumerate(trigger.should)]
    prompts += [(False, len(trigger.should) + index, prompt) for index, prompt in enumerate(trigger.should_not)]
    with tempfile.TemporaryDirectory(prefix="guidance-trigger-") as temporary:
        for should, replicate, prompt in prompts:
            case = _temporary_case(Path(temporary) / str(replicate), prompt, max_time="2m")
            spec = make_spec(runner.seed.snapshot_hash, runner.guidance,
                {"image": runner.seed.image, "roles": runner.roles, "trigger": skill,
                 "window": trigger.window, "readonly": True}, case, replicate=replicate)
            specs.append(spec)
            if runner.store.needs_trial(spec.id):
                runner.account_trials(specs, ledger)
                cap = runner.trial_cap(spec)
                if not ledger.admit(cap):
                    stop_reason = "budget"
                    break
                try:
                    runner.store.save_trial(spec, runner.run_trial(spec, readonly=True))
                finally:
                    ledger.release(cap)
            result = runner.store.load_trial(spec.id).result
            if result.status != "complete":
                raise RuntimeError(f"trigger trial infrastructure failed: {result.error}")
            evidence = extract_events(runner.store.trial_path(spec.id) / "events.jsonl")
            results.append({"should": should, "loaded": skill_loaded(evidence["commands"], skill, trigger.window),
                            "trial": spec.id})
        runner.account_trials(specs, ledger)
    should_results = [r["loaded"] for r in results if r["should"]]
    near_misses = [r["loaded"] for r in results if not r["should"]]
    complete = stop_reason is None
    report = {"skill": skill, "complete": complete, "stop_reason": stop_reason,
              "recall": sum(should_results) / len(trigger.should) if complete else None,
              "false_positive_rate": sum(near_misses) / len(trigger.should_not) if complete else None,
              "spent": ledger.spent, "budget": ledger.limit, "results": results}
    atomic_write(runner.store.root / "triggers" / f"{skill}.json", (json.dumps(report, indent=2) + "\n").encode())
    return report


def execute_command(args: argparse.Namespace) -> int:
    root = Path(args.project).resolve() if args.project is not None else Path.cwd()
    if args.command in {"run", "triggers"}:
        if not args.free and args.budget is None:
            raise ValueError("Ask the user for a run budget; pass it as --budget USD (or use --free)")
        RunBudget(args.budget)
    if args.command == "smoke" and args.budget is not None:
        RunBudget(args.budget)
    result: dict[str, Any]
    project: Project | None = None
    if args.store and (args.command == "janitor" or (args.command == "status" and args.project is None)):
        db = Store(Path(args.store))
    else:
        project = load_toml(root / ".omp/evals/project.toml", Project)
        db = Store(Path(args.store)) if args.store else Store.for_project(project.slug, project.results)
    if args.command == "janitor":
        result = {**janitor(db.root), **reap_dispatchers(db.root)}
    elif args.command == "status":
        manifests = list((db.root / "trials").glob("*/manifest.json"))
        cases = discover_cases(root, project) if project is not None else []
        trials = [db.load_trial(p.parent.name) for p in manifests]
        admissions = admission_status(root, project, db) if project is not None else {
            "admitted": 0, "stale_admissions": [
                {"id": path.parent.name, "reasons": ["project required to validate admission"]}
                for path in (db.root / "admissions").glob("*/admission.json")]}
        result = {"project": project.slug if project else None, "cases": [case.key for case in cases],
                  "store": str(db.root), "complete": sum(t.result.status == "complete" for t in trials),
                  "infra_error": sum(t.result.status == "infra_error" for t in trials), **admissions}
    else:
        if project is None:
            raise ValueError("project configuration required")
        free = (args.command == "smoke" and args.budget is None) or bool(getattr(args, "free", False))
        with prepared(root, project, db, free=free) as runner:
            if args.command == "smoke":
                result = _smoke(runner, str(args.prompt), args.budget)
            elif args.command == "admit":
                result = {"cases": admit_cases(runner, discover_cases(root, project), list(args.cases), jobs=args.jobs),
                          "untracked_in_seed": untracked_in_seed(root, project)}
                if not result["cases"]:
                    raise ValueError("no cases matched admission selectors")
            elif args.command == "triggers":
                result = measure_triggers(runner, str(args.skill), args.budget)
            else:
                result = run_experiment(runner, Path(args.experiment),
                    int(args.jobs) if args.jobs is not None else jobs_default(), budget=args.budget)
    print(json.dumps(result))
    return 2 if result.get("stop_reason") == "first-wave-infra" else 0
