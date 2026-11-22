"""Grade a trial iteration's expectations with omp's judge, from a Python eval cell.

    exec(read("skill://testing-guidance/scripts/grade.py"))
    await grade(Path("<iteration dir>"), judge_batch, completion)

Each run's expectations go to `judge_batch` as yes/no questions over a state holding only the
task, the final answer, the diff and the check results, never the arm. A verdict between 0.2 and
0.8 gets a second opinion with evidence from `completion` on the slow model. Each eval then gets
one critique of its expectations (eval_feedback.json). Writes grading.json into every run dir.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

UNCERTAIN = (0.2, 0.8)
RUBRIC = (
    "The state shows a coding agent's task, its final answer, the diff of the files it changed and the "
    "results of automated checks. Judge only from that evidence. Answer yes only when the evidence shows "
    "the expectation holds in substance; wording that claims it without the work counts as no, and so does "
    "missing evidence. Expectation: "
)
SECOND = {
    "type": "object",
    "properties": {"passed": {"type": "boolean"}, "evidence": {"type": "string"}},
    "required": ["passed", "evidence"],
}
CRITIQUE = {
    "type": "object",
    "properties": {
        "weak": {"type": "array", "items": {"type": "object", "properties": {"expectation": {"type": "string"}, "reason": {"type": "string"}},
                                            "required": ["expectation", "reason"]}},
        "missing": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["weak", "missing"],
}


LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb", "Cargo.lock", "poetry.lock", "uv.lock", "Gemfile.lock", "go.sum"}


def without_lockfiles(diff: str) -> str:
    """The diff with each lockfile's hunks replaced by one line, so real changes fit in the grader's view."""
    parts = re.split(r"(?m)^(?=diff --git )", diff)
    kept = []
    for part in parts:
        header = part.split("\n", 1)[0]
        if Path(header.rsplit(" b/", 1)[-1]).name in LOCKFILES:
            kept.append(f"{header}\n[lockfile changed; contents omitted]\n")
        else:
            kept.append(part)
    return "".join(kept)


def state(run_dir: Path, target: str) -> dict:
    """What the grader sees of one run: never the arm, and the target's name masked."""
    metrics = json.loads((run_dir / "metrics.json").read_text())
    checks = json.loads((run_dir / "checks.json").read_text()) if (run_dir / "checks.json").exists() else []
    diff = without_lockfiles((run_dir / "diff.patch").read_text()) if (run_dir / "diff.patch").exists() else ""
    mask = re.compile(re.escape(target), re.IGNORECASE)
    final = mask.sub("[the guidance]", (run_dir / "final.md").read_text()[:20_000])
    changes = mask.sub("[the guidance]", diff[:30_000]) + ("\n[diff truncated]" if len(diff) > 30_000 else "")
    return {"task": metrics.get("prompt", ""), "final_answer": final, "changes": changes,
            "checks": [{"name": c["name"], "passed": c["passed"]} for c in checks]}


def question(text: str) -> dict:
    return {"type": "bool", "instructions": RUBRIC + text,
            "criteria": {"true": "The evidence shows it holds.", "false": "It does not hold, or the evidence does not show it."}}


async def resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def ask_slow(completion: Callable, prompt: str, system: str, schema: dict) -> Any:
    """One `completion` call on the slow model; its handle's `wait()` is sync in Python eval, async in tests."""
    handle = completion(prompt, model="slow", system=system, schema=schema)
    return await resolve(handle.wait())


async def grade(out: Path, judge_batch: Callable, completion: Callable, critique: bool = True) -> None:
    out = Path(out)
    index = json.loads((out / "index.json").read_text())
    feedback: dict[str, Any] = {}
    for ev_id, spec in index["evals"].items():
        expectations = spec.get("expectations") or []
        runs = [r["dir"] for r in index["runs"] if r["eval"] == ev_id and r.get("status") == "done"]
        if not expectations or not runs:
            continue
        states = {d: state(out / d, index["name"]) for d in runs}
        questions = {f"e{i}": question(t) for i, t in enumerate(expectations)}
        batch = judge_batch(states, questions, intent=f"Grading {ev_id}")
        verdicts: dict[str, dict] = {}
        async for key, item in batch.drain_iter(1800):
            if not item.ok:
                raise RuntimeError(f"judge failed on {key}: {item.error}")
            verdicts[key] = item.answers
        for d in runs:
            if d not in verdicts:
                raise RuntimeError(f"the judge returned no verdict for {d}; rerun grade()")
            graded = []
            for i, text in enumerate(expectations):
                p = float(verdicts[d][f"e{i}"]["bool"])
                entry = {"text": text, "passed": p >= 0.5, "p_yes": round(p, 3), "evidence": ""}
                if UNCERTAIN[0] < p < UNCERTAIN[1]:
                    prompt = json.dumps({"state": states[d], "expectation": text})
                    second = await ask_slow(completion, prompt, RUBRIC + "the one in the input.", SECOND)
                    entry.update(passed=bool(second["passed"]), evidence=second["evidence"], second_opinion=True)
                graded.append(entry)
            (out / d / "grading.json").write_text(json.dumps({"expectations": graded}, indent=2))
        if critique:
            sample = [{"state": states[d], "verdicts": json.loads((out / d / "grading.json").read_text())["expectations"]} for d in runs[:4]]
            prompt = json.dumps({"task": spec["prompt"], "expectations": expectations, "graded_runs": sample})
            system = ("You review an eval's expectations. List expectations that a wrong or lazy output would also pass "
                      "(weak), and important outcomes visible in the runs that no expectation checks (missing). "
                      "Raise only gaps the eval author would act on.")
            feedback[ev_id] = await ask_slow(completion, prompt, system, CRITIQUE)
    if critique:
        (out / "eval_feedback.json").write_text(json.dumps(feedback, indent=2))
