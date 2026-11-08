from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Barrier, Event, Lock
from typing import Any

import pytest

from guidance_evals.contracts import Agent, Case, Check, Checks, DiscoveredCase, Image, Project
from guidance_evals.dispatcher import Dispatcher
from guidance_evals.runtime import RealRunner, admit_cases
from guidance_evals.sandbox import Sandbox, SeedInfo
from guidance_evals.store import Store, atomic_write


@pytest.fixture
def environment(tmp_path: Path) -> tuple[RealRunner, list[DiscoveredCase]]:
    project = Project(slug="admission", image=Image(containerfile="Containerfile"),
                      agent=Agent(roles={"default": "provider/model"}))
    store = Store(tmp_path / "store")
    runner = RealRunner(tmp_path, project, store, Dispatcher(tmp_path / "dispatcher"),
        Sandbox(tmp_path, project, store.root, "admission-test"),
        SeedInfo("image", tmp_path, "snapshot"), {})
    cases: list[DiscoveredCase] = []
    for name in ("alpha", "beta", "gamma", "delta"):
        path = tmp_path / name
        (path / "verifier").mkdir(parents=True)
        (path / "verifier/verify.sh").write_text("exit 0\n")
        (path / "reference.patch").write_text("reference patch\n")
        cases.append(DiscoveredCase(spec=Case(id=name, targets=["all"], prompt="Fix the bug."),
            family="family", path=path, case_hash=f"hash-{name}"))
    return runner, cases


def outcome(patch: Path) -> Checks:
    return Checks(checks=[Check(id="completion", passed=patch.name == "reference.patch")])


def assert_records(runner: RealRunner, records: list[dict[str, Any]]) -> None:
    for record in records:
        path = runner.store.root / "admissions" / record["admission_id"] / "admission.json"
        assert json.loads(path.read_text()) == record
        assert record["snapshot"] == "snapshot"
        assert record["image"] == "image"
        assert record["case_hash"] == "hash-" + record["case"].split("/")[1]
        assert {"agent_hash", "verifier_hash", "reference_hash", "admission_id"} <= record.keys()
        assert record["admitted"] is True
        assert record["reason"] == "admitted"
        assert [run["checks"][0]["passed"] for run in record["reference"]] == [True, True]
        assert [run["checks"][0]["passed"] for run in record["base"]] == [False, False]


@pytest.mark.parametrize("jobs", [None, 2])
def test_distinct_cases_overlap_preserve_verify_sequence_and_result_order(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch,
    jobs: int | None,
) -> None:
    runner, cases = environment
    rendezvous = Barrier(2, timeout=5)
    beta_finished = Event()
    calls: dict[str, list[str]] = {"alpha": [], "beta": []}
    finished: list[str] = []
    outputs: set[Path] = set()
    lock = Lock()
    monkeypatch.setattr("guidance_evals.runtime.jobs_default", lambda: 2)

    def verify(seed: SeedInfo, case: Case, case_dir: Path, patch: Path, output: Path) -> Checks:
        assert seed is runner.seed
        assert case_dir == next(item.path for item in cases if item.spec.id == case.id)
        with lock:
            calls[case.id].append(output.name)
            assert output not in outputs
            outputs.add(output)
        if output.name == "reference-0":
            rendezvous.wait()
            if case.id == "alpha":
                assert beta_finished.wait(5), "beta must finish while alpha remains active"
        if output.name == "base-1":
            finished.append(case.id)
            if case.id == "beta":
                beta_finished.set()
        return outcome(patch)

    monkeypatch.setattr(runner.sandbox, "verify", verify)
    records = admit_cases(runner, cases[:2], [], jobs=jobs)
    assert finished == ["beta", "alpha"]
    assert calls == {name: ["reference-0", "base-0", "reference-1", "base-1"] for name in calls}
    assert [record["case"] for record in records] == ["family/alpha", "family/beta"]
    assert len(outputs) == 8
    assert_records(runner, records)


def test_jobs_bounds_concurrent_verifiers(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, cases = environment
    release = Event()
    first_wave = Event()
    lock = Lock()
    active = 0
    peak = 0

    def verify(_seed: SeedInfo, _case: Case, _case_dir: Path, patch: Path, _output: Path) -> Checks:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 2:
                first_wave.set()
        try:
            assert release.wait(5), "controller must release verifier workers"
            return outcome(patch)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(runner.sandbox, "verify", verify)
    with ThreadPoolExecutor(max_workers=1) as caller:
        result = caller.submit(admit_cases, runner, cases, [], jobs=2)
        try:
            assert first_wave.wait(5), "two workers must reach verification concurrently"
            with lock:
                assert active == 2
        finally:
            release.set()
        records = result.result(timeout=5)
    assert peak == 2
    assert active == 0
    assert_records(runner, records)


def test_jobs_one_runs_whole_cases_serially(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, cases = environment
    calls: list[tuple[str, str]] = []

    def verify(_seed: SeedInfo, case: Case, _case_dir: Path, patch: Path, output: Path) -> Checks:
        calls.append((case.id, output.name))
        return outcome(patch)

    monkeypatch.setattr(runner.sandbox, "verify", verify)
    records = admit_cases(runner, cases[:2], [], jobs=1)
    assert calls == [(name, step) for name in ("alpha", "beta")
                     for step in ("reference-0", "base-0", "reference-1", "base-1")]
    assert_records(runner, records)


@pytest.mark.parametrize("jobs", [0, -1])
def test_nonpositive_jobs_fail_before_verification(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch, jobs: int,
) -> None:
    runner, cases = environment

    def verify(*_args: object) -> Checks:
        pytest.fail("invalid jobs must fail before any verifier runs")

    monkeypatch.setattr(runner.sandbox, "verify", verify)
    with pytest.raises(ValueError, match="jobs must be positive"):
        admit_cases(runner, cases, [], jobs=jobs)
    assert not list((runner.store.root / "admissions").glob("*/admission.json"))


@pytest.mark.parametrize("invalid", ["prompt", "frozen", "reference", "saved-json"])
def test_all_selected_cases_preflight_before_any_verifier(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch, invalid: str,
) -> None:
    runner, cases = environment
    if invalid == "prompt":
        cases[1].spec.prompt = "Read RULES.md and fix the bug."
    elif invalid == "reference":
        (cases[1].path / "reference.patch").unlink()
    else:
        saved = runner.store.root / "admissions/old/admission.json"
        data = json.dumps({"admission_id": "old", "case": cases[1].key,
                           "case_hash": "old", "admitted": True}) if invalid == "frozen" else "invalid JSON"
        atomic_write(saved, data.encode())

    def verify(*_args: object) -> Checks:
        pytest.fail("all selected cases must pass preflight before starting any verifier")

    monkeypatch.setattr(runner.sandbox, "verify", verify)
    with pytest.raises((ValueError, OSError)):
        admit_cases(runner, cases[:2], [])


def test_selectors_exclude_invalid_cases_before_preflight(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, cases = environment
    cases[1].spec.prompt = "Read RULES.md."
    (cases[1].path / "reference.patch").unlink()

    def verify(_seed: SeedInfo, _case: Case, _case_dir: Path, patch: Path, _output: Path) -> Checks:
        return outcome(patch)

    monkeypatch.setattr(runner.sandbox, "verify", verify)
    records = admit_cases(runner, cases, ["alpha"], jobs=2)
    assert [record["case"] for record in records] == ["family/alpha"]
    assert_records(runner, records)


def test_saved_admissions_are_read_once_for_all_cases(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, cases = environment
    saved = runner.store.root / "admissions/old/admission.json"
    atomic_write(saved, b'{"admission_id":"old","case":"family/removed","admitted":true}')
    original = Path.read_text
    reads = 0

    def read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        nonlocal reads
        if path == saved:
            reads += 1
        return original(path, *args, **kwargs)

    def verify(_seed: SeedInfo, _case: Case, _case_dir: Path, patch: Path, _output: Path) -> Checks:
        return outcome(patch)

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(runner.sandbox, "verify", verify)
    records = admit_cases(runner, cases, [])
    assert reads == 1
    assert_records(runner, records)


def test_infrastructure_failure_isolated_to_its_case(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, cases = environment
    calls: dict[str, list[str]] = {"alpha": [], "beta": []}

    def verify(_seed: SeedInfo, case: Case, _case_dir: Path, patch: Path, output: Path) -> Checks:
        calls[case.id].append(output.name)
        if case.id == "alpha" and output.name == "reference-1":
            raise RuntimeError("verifier unavailable")
        return outcome(patch)

    monkeypatch.setattr(runner.sandbox, "verify", verify)
    records = admit_cases(runner, cases[:2], [], jobs=2)
    failed, passed = records
    assert failed["admitted"] is False
    assert failed["status"] == "infra_error"
    assert failed["reason"] == "RuntimeError: verifier unavailable"
    assert "reference" not in failed and "base" not in failed
    assert calls["alpha"] == ["reference-0", "base-0", "reference-1"]
    assert calls["beta"] == ["reference-0", "base-0", "reference-1", "base-1"]
    path = runner.store.root / "admissions" / failed["admission_id"] / "admission.json"
    assert json.loads(path.read_text()) == failed
    assert_records(runner, [passed])


@pytest.mark.parametrize(("failure", "reason"), [
    ("reference", "reference does not pass every check"),
    ("base", "base does not fail completion or a critical targeted check"),
    ("unstable", "verifier runs disagree"),
])
def test_failed_admission_preserves_existing_decision_semantics(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch,
    failure: str, reason: str,
) -> None:
    runner, cases = environment

    def verify(_seed: SeedInfo, _case: Case, _case_dir: Path, patch: Path, output: Path) -> Checks:
        passed = patch.name == "reference.patch"
        if failure == "reference" and passed:
            passed = False
        elif failure == "base" and not passed:
            passed = True
        elif failure == "unstable" and output.name == "reference-1":
            passed = False
        return Checks(checks=[Check(id="completion", passed=passed)])

    monkeypatch.setattr(runner.sandbox, "verify", verify)
    record, = admit_cases(runner, cases[:1], [], jobs=2)
    assert record["admitted"] is False
    assert record["reason"] == reason
    assert "status" not in record
    assert len(record["reference"]) == 2
    assert len(record["base"]) == 2
    path = runner.store.root / "admissions" / record["admission_id"] / "admission.json"
    assert json.loads(path.read_text()) == record


def test_interruption_cancels_owned_work_and_awaits_worker_cleanup(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, cases = environment
    rendezvous = Barrier(2, timeout=5)
    cancelled = Event()
    cleaned = Event()

    def cancel() -> None:
        runner.sandbox.cancelled.set()
        cancelled.set()

    def verify(_seed: SeedInfo, case: Case, _case_dir: Path, _patch: Path, _output: Path) -> Checks:
        rendezvous.wait()
        if case.id == "beta":
            raise KeyboardInterrupt()
        try:
            assert cancelled.wait(5), "interruption must cancel engine-owned work"
            raise RuntimeError("cancelled")
        finally:
            cleaned.set()

    monkeypatch.setattr(runner.sandbox, "cancel", cancel)
    monkeypatch.setattr(runner.sandbox, "verify", verify)
    with pytest.raises(KeyboardInterrupt):
        admit_cases(runner, cases[:2], [], jobs=2)
    assert cancelled.is_set()
    assert cleaned.is_set()


@pytest.mark.parametrize("jobs", [1, 2])
def test_sigterm_uses_owned_cleanup_and_restores_previous_handler(
    environment: tuple[RealRunner, list[DiscoveredCase]], monkeypatch: pytest.MonkeyPatch,
    jobs: int,
) -> None:
    import signal
    from types import FrameType
    runner, cases = environment
    cancelled, cleaned = Event(), Event()

    def previous(_signum: int, _frame: FrameType | None) -> None:
        raise AssertionError("admission did not install its SIGTERM cleanup handler")

    def verify(_seed: SeedInfo, _case: Case, _case_dir: Path, _patch: Path, _output: Path) -> Checks:
        try:
            handler = signal.getsignal(signal.SIGTERM)
            assert callable(handler)
            handler(signal.SIGTERM, None)
            raise AssertionError("SIGTERM handler must interrupt admission")
        finally:
            cleaned.set()

    monkeypatch.setattr(runner.sandbox, "verify", verify)
    monkeypatch.setattr(runner.sandbox, "cancel", cancelled.set)
    original = signal.signal(signal.SIGTERM, previous)
    try:
        with pytest.raises(SystemExit) as interrupted:
            admit_cases(runner, cases[:1], [], jobs=jobs)
        assert interrupted.value.code == 128 + signal.SIGTERM
        assert cancelled.is_set() and cleaned.is_set()
        assert signal.getsignal(signal.SIGTERM) is previous
    finally:
        signal.signal(signal.SIGTERM, original)
