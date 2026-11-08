"""Argparse adapter; structured stdout is JSON, diagnostics are stderr."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import subprocess

from pydantic import Field

from .analysis import Analysis, analyze
from .contracts import validate_target
from .contracts import ContractError, StrictModel, Project, discover_cases, load_json, load_toml
from .identity import IdentityInputs, content_hash, engine_hash
from .plan import Experiment, advance_look, expand_experiments, plan_trials, removed_targets
from .report import write_report
from .runner import FakeRunner, TrialSpec
from .store import Store, atomic_model, atomic_write


class FrozenPlan(StrictModel):
    experiment: Experiment
    trials: list[TrialSpec]
    protected: list[str] = Field(default_factory=list[str])
    blocks: dict[str, list[str]] = Field(default_factory=dict)
    smoke_only: bool = False
    grading_verifiers: dict[str, str] = Field(default_factory=dict)
    grading_judges: dict[str, str] = Field(default_factory=dict)
    grading_engines: dict[str, str] = Field(default_factory=dict)
    agent_roles: dict[str, str] = Field(default_factory=dict)


class PlanIdentity(StrictModel):
    snapshot: str
    arm_hashes: dict[str, str]
    agent_hash: str
    engine_hash: str | None = None


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="guidance-evals", description="Plan, resume and analyze paired guidance trials. Structured output is JSON.")
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate project and discover cases")
    validate.add_argument("--project", type=Path, required=True, help="project root")
    plan = commands.add_parser("plan", help="expand strategy, freeze comparisons; emit missing trials")
    plan.add_argument("--project", type=Path, required=True)
    plan.add_argument("--experiment", type=Path, required=True, help="experiment TOML: name, kind, optional selectors/block/ref")
    plan.add_argument("--identity", type=Path, required=True, help="JSON: snapshot, arm_hashes, agent_hash; optional engine_hash")
    plan.add_argument("--store", type=Path, help="override project result store")
    plan.add_argument("--next-look", action="store_true", help="advance unresolved comparisons, all cases balanced: 3 -> 6")
    selftest_cmd = commands.add_parser("selftest", help="populate FakeRunner positive control (no network)")
    selftest_cmd.add_argument("--store", type=Path, required=True)
    analyze_cmd = commands.add_parser("analyze", help="write Markdown + JSON reports from a frozen comparison")
    analyze_cmd.add_argument("--store", type=Path, required=True)
    analyze_cmd.add_argument("--experiment", default="selftest", help="frozen comparison name (default: selftest)")
    analyze_cmd.add_argument("--with-arm", help="default: comparison's first arm")
    analyze_cmd.add_argument("--without-arm", help="default: comparison's second arm")
    analyze_cmd.add_argument("--target", help="override frozen relevant targets (target or frozen block name)")
    analyze_cmd.add_argument("--verifier-hash", help="select a grading version")
    analyze_cmd.add_argument("--judge-hash", help="select a grading version")
    analyze_cmd.add_argument("--engine-hash", help="select a saved grading-engine version")
    analyze_cmd.add_argument("--output", type=Path, help="report directory (default: STORE/reports/COMPARISON)")
    analyze_cmd.add_argument("--project", type=Path, help="regrade saved artifacts with this project's current judge; never run agents")
    descriptions = {
        "run": "execute or resume a frozen experiment and grade missing outcomes",
        "admit": "validate reference/base outcomes and store stable admissions",
        "triggers": "measure a skill's positive and near-miss discovery",
        "smoke": "exercise one isolated free-model trial and collect evidence",
        "status": "validate project inputs and summarize stored outcomes",
        "janitor": "reap dead runs' owned sandboxes and dispatchers",
    }
    for name, description in descriptions.items():
        command = commands.add_parser(name, help=description)
        command.add_argument("--project", type=Path, help="project root (default: current directory)")
        command.add_argument("--store", type=Path)
        if name == "run":
            command.add_argument("experiment", type=Path)
            command.add_argument("--jobs", type=int)
            command.add_argument("--budget", type=float, metavar="USD", help="user-approved total run budget; required unless --free")
            command.add_argument("--free", action="store_true", help="smoke-only free model, not production evidence")
        elif name == "admit":
            command.add_argument("cases", nargs="*")
            command.add_argument("--jobs", type=int, help="maximum concurrent case admissions (default: up to 4)")
        elif name == "triggers":
            command.add_argument("skill")
            command.add_argument("--budget", type=float, metavar="USD", help="user-approved budget; required unless --free")
            command.add_argument("--free", action="store_true", help="smoke-only free model, not production evidence")
        elif name == "smoke":
            command.add_argument("--prompt", default="Add a file guidance-evals-smoke.txt containing exactly sandbox-ok followed by a newline. Report what you changed.")
            command.add_argument("--budget", type=float, metavar="USD",
                                 help="user-approved budget; runs the smoke trial on the production model instead of the free smoke_model")
    return root


def plan_path(db: Store, name: str) -> Path:
    Experiment(name=name)
    return db.root / "experiments" / name / "plan.json"


def analyze_plan(db: Store, frozen: FrozenPlan, *, with_arm: str | None = None,
             without_arm: str | None = None, target: str | None = None,
             verifier_hash: str | None = None, judge_hash: str | None = None,
             engine_hash: str | None = None) -> Analysis:
    first = with_arm or frozen.experiment.arms[0]
    second = without_arm or frozen.experiment.arms[1]
    if first not in frozen.experiment.arms or second not in frozen.experiment.arms:
        raise ValueError("comparison arms must belong to the frozen experiment")
    removed = second.removeprefix("minus:") if second.startswith("minus:") else "all"
    if target is not None:
        label = target
        members = frozen.blocks[target] if target in frozen.blocks else [validate_target(target)]
    elif frozen.experiment.relevant_targets:
        relevant = list(dict.fromkeys(frozen.experiment.relevant_targets))
        shared = set(removed_targets(first, frozen.blocks)) & set(removed_targets(second, frozen.blocks))
        members = [member for member in relevant if member not in shared] or relevant
        label = (members[0] if len(members) == 1 else removed
                 if set(frozen.blocks.get(removed, [])) == set(members)
                 else "targets: " + ", ".join(members))
    else:
        label = removed
        members = frozen.blocks[removed] if removed in frozen.blocks else [validate_target(removed)]
    observations = db.observations(
        specs=frozen.trials, exposure_targets=members,
        grading_versions={spec.id: (
            verifier_hash or frozen.grading_verifiers.get(spec.id),
            judge_hash or frozen.grading_judges.get(spec.id),
            engine_hash or frozen.grading_engines.get(spec.id),
        ) for spec in frozen.trials},
    )
    result = analyze(observations, first, second, target=label, protected=frozen.protected, members=members,
                     final_look=max(frozen.experiment.looks))
    if frozen.smoke_only:
        result.verdict = "inconclusive"
        result.action = "smoke only; do not change project guidance"
        result.warnings.append("free/local model trials test the harness, not project guidance")
    return result


def selftest(db: Store) -> FrozenPlan:
    exp = Experiment(name="selftest")
    specs: list[TrialSpec] = []
    engine = engine_hash()
    for index in range(10):
        for replicate in range(3):
            for arm in exp.arms:
                ident = IdentityInputs(snapshot=content_hash("synthetic-code"), arm=content_hash(arm),
                    case=content_hash(f"control-{index}"), agent=content_hash("FakeRunner-v1"),
                    engine=engine, replicate=replicate)
                specs.append(TrialSpec(identity=ident, arm=arm, case_key=f"control-{index}/positive",
                                       family=f"control-{index}", targets=["all"]))
    frozen = FrozenPlan(experiment=exp, trials=specs)
    fake = FakeRunner()
    for spec in specs:
        if db.needs_trial(spec.id):
            # FakeRunner never supplies authoritative exposure. Exercise the same
            # frozen-artifact reader as paid trials, with explicit synthetic data.
            files = {"AGENTS.md": "c3ludGhldGljCg=="} if spec.arm == "current" else {}
            directory = db.trial_path(spec.id)
            atomic_write(directory / "baseline-guidance.json", (json.dumps(files) + "\n").encode())
            atomic_write(directory / "events.jsonl", b'{"type":"agent_end"}\n')
            outcome = fake.run_trial(spec).model_copy(update={"artifacts": {
                "baseline-guidance.json": "baseline-guidance.json", "events.jsonl": "events.jsonl"}})
            db.save_trial(spec, outcome)
        if db.needs_grade(spec.id, content_hash("fake-verifier-v1"), content_hash("no-judge")):
            db.save_grade(spec.id, content_hash("fake-verifier-v1"), content_hash("no-judge"),
                          fake.grade(db.load_trial(spec.id)))
    atomic_model(plan_path(db, exp.name), frozen)
    return frozen


def _plan_command(args: argparse.Namespace) -> None:
    project_root = Path(args.project)
    project = load_toml(project_root / ".omp/evals/project.toml", Project)
    strategy = load_toml(Path(args.experiment), Experiment).model_copy(update={"holdout": project.holdout})
    identities = load_json(Path(args.identity), PlanIdentity)
    cases = discover_cases(project_root, project)
    db = Store(Path(args.store)) if args.store else Store.for_project(project.slug, project.results)
    expanded = expand_experiments(strategy, project.blocks)
    output: list[dict[str, object]] = []
    for exp in expanded.comparisons:
        path = plan_path(db, exp.name)
        old = load_json(path, FrozenPlan) if path.exists() else None
        if args.next_look:
            if old is None:
                raise ValueError("next look requires a frozen first look")
            result = analyze_plan(db, old)
            if result.infra_errors:
                raise ValueError("finish and grade the first look before advancing")
            advanced = advance_look(old.experiment, result.verdict)
            if advanced is None:
                continue
            exp = advanced
        specs = plan_trials(exp, cases, snapshot=identities.snapshot, arm_hashes=identities.arm_hashes,
            agent_hash=identities.agent_hash, engine_hash=identities.engine_hash or engine_hash())
        if not specs:
            raise ValueError("no cases match selectors, relevance and split")
        frozen = FrozenPlan(experiment=exp, trials=specs, protected=project.protected, blocks=expanded.blocks)
        if old is not None and old != frozen:
            old_ids = {s.id for s in old.trials}
            # The only permitted mutation is extending the very same comparison's look.
            base = frozen.model_copy(update={"experiment": frozen.experiment.model_copy(update={"replicates": old.experiment.replicates}),
                                             "trials": [s for s in specs if s.id in old_ids]})
            if not args.next_look or base != old:
                raise ValueError("experiment name already frozen with different inputs; use a new name")
        atomic_model(path, frozen)
        output.append({"name": exp.name, "trials": [s.model_dump(mode="json") for s in specs if db.needs_trial(s.id)]})
    print(json.dumps({"store": str(db.root), "comparisons": output, "blocks": expanded.blocks}))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            project_root = Path(args.project)
            project = load_toml(project_root / ".omp/evals/project.toml", Project)
            cases = discover_cases(project_root, project)
            print(json.dumps({"project": project.slug, "cases": [{"key": c.key, "hash": c.case_hash, "targets": c.spec.targets} for c in cases]}))
        elif args.command == "plan":
            _plan_command(args)
        elif args.command in {"run", "admit", "triggers", "smoke", "status", "janitor"}:
            from .commands import execute_command
            return execute_command(args)
        elif args.command == "selftest":
            db = Store(Path(args.store))
            frozen = selftest(db)
            print(json.dumps({"store": str(db.root), "experiment": frozen.experiment.name, "trials": len(frozen.trials)}))
        elif args.command == "analyze":
            db = Store(Path(args.store))
            frozen = load_json(plan_path(db, str(args.experiment)), FrozenPlan)
            regraded = 0
            if args.project is not None:
                from .commands import regrade_plan
                regraded = regrade_plan(Path(args.project), db, frozen)
                atomic_model(plan_path(db, str(args.experiment)), frozen)
            result = analyze_plan(db, frozen, with_arm=args.with_arm, without_arm=args.without_arm, target=args.target,
                              verifier_hash=args.verifier_hash, judge_hash=args.judge_hash, engine_hash=args.engine_hash)
            directory = Path(args.output) if args.output else db.root / "reports" / frozen.experiment.name
            md, data = write_report(result, directory)
            print(json.dumps({"verdict": result.verdict, "action": result.action, "regraded": regraded,
                              "markdown": str(md), "json": str(data)}))
    except KeyboardInterrupt:
        print(json.dumps({"error": "run interrupted; repeat run to resume"}), file=sys.stderr)
        return 130
    except (ContractError, ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if isinstance(exc, OSError):
            message = "filesystem operation failed"
        elif isinstance(exc, subprocess.SubprocessError):
            message = "infrastructure command failed; inspect run artifacts"
        else:
            message = str(exc)
        print(json.dumps({"error": message}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
