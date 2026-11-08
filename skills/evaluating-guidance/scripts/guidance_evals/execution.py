from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any, Literal, TypedDict, cast
import uuid

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .contracts import Budget, Checks, Judge, JudgeSettings, load_toml
from .dispatcher import Dispatcher
from .runner import GradedCheck


class ExtractedEvents(TypedDict):
    commands: list[dict[str, Any]]
    final_answer: str


class NativeAnswer(BaseModel):
    model_config = ConfigDict(strict=True)
    type: Literal["noul"]
    noul: float = Field(ge=0, le=1, allow_inf_nan=False)


class NativeJudgment(BaseModel):
    model_config = ConfigDict(strict=True)
    answers: dict[str, NativeAnswer]


def redact_artifacts(root: Path, token: str) -> bool:
    """Credentials may be echoed by tools; never forward them to a judge."""
    leaked_diff = False
    secret = token.encode()
    if not secret:
        return False
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if secret in data:
            leaked_diff |= path.name == "diff.patch"
            path.write_bytes(data.replace(secret, b"[REDACTED_TRIAL_TOKEN]"))
    return leaked_diff


def effective_budget(case: Budget, project: Budget) -> Budget:
    def seconds(duration: str) -> int:
        return int(duration[:-1]) * {"s": 1, "m": 60, "h": 3600}[duration[-1]]
    return Budget(max_time=min([case.max_time, project.max_time], key=seconds),
                  max_cost=min(case.max_cost, project.max_cost))


def prompt_names_guidance(prompt: str, targets: list[str]) -> bool:
    if re.search(r"(?:skill|rule)://|\.omp/(?:rules|skills)|\b(?:AGENTS|RULES)\.md\b", prompt, re.IGNORECASE):
        return True
    for target in targets:
        kind, _, name = target.removeprefix("user-").partition(":")
        if kind in {"rule", "skill"} and re.search(
                rf"\b(?:{kind}\s+{re.escape(name)}|{re.escape(name)}\s+{kind})\b", prompt, re.IGNORECASE):
            return True
    return False


def admission_decision(reference: list[Checks], base: list[Checks]) -> tuple[bool, str]:
    if len(reference) != 2 or len(base) != 2:
        return False, "two runs per tree required"
    def outcomes(checks: Checks) -> set[tuple[str, bool, bool, tuple[str, ...]]]:
        return {(c.id, c.passed, c.critical, tuple(c.targets)) for c in checks.checks}

    if outcomes(reference[0]) != outcomes(reference[1]) or outcomes(base[0]) != outcomes(base[1]):
        return False, "verifier runs disagree"
    if not all(check.passed for check in reference[0].checks):
        return False, "reference does not pass every check"
    if not any(not check.passed and (check.id == "completion" or (check.critical and check.targets))
               for check in base[0].checks):
        return False, "base does not fail completion or a critical targeted check"
    if {(c.id, c.critical, tuple(c.targets)) for c in reference[0].checks} != {
            (c.id, c.critical, tuple(c.targets)) for c in base[0].checks}:
        return False, "reference and base check definitions differ"
    return True, "admitted"


def judge_verdict(probability: float, pass_threshold: float, fail_threshold: float) -> bool | None:
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("judge probability outside [0,1]")
    return True if probability >= pass_threshold else False if probability <= fail_threshold else None


def skill_loaded(calls: list[dict[str, Any]], skill: str, window: int) -> bool:
    expected = f"skill://{skill}"
    for call in calls[:window]:
        if call.get("name") != "read":
            continue
        path = call.get("arguments", {}).get("path", "")
        if isinstance(path, str) and (path == expected or path.startswith(expected + "/")):
            return True
    return False


def extract_events(path: Path) -> ExtractedEvents:
    calls: list[dict[str, Any]] = []
    final_answer = ""
    if not path.exists():
        raise ValueError("agent events artifact missing")
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            decoded: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"agent events line {line_number}: invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ValueError(f"agent events line {line_number}: expected object")
        event = cast(dict[str, Any], decoded)
        kind = event.get("type")
        if kind == "tool_execution_start":
            calls.append({"name": event.get("toolName"), "arguments": event.get("args", {})})
        if kind == "message_end":
            message = event.get("message", {})
            if message.get("role") == "assistant":
                if message.get("stopReason") == "error":
                    error = str(message.get("errorMessage", ""))
                    if "budget exhausted" in error.lower():
                        raise RuntimeError("dispatcher 429 Budget exhausted")
                    if "unmeasured" in error.lower():
                        raise RuntimeError("dispatcher usage accounting incomplete")
                    status = re.search(r"\b([45]\d{2})\b", error)
                    if status:
                        code = status.group(1)
                        suffix = " rate limit" if code == "429" else ""
                        raise RuntimeError(f"provider {code}{suffix}")
                    raise RuntimeError("model request failed; inspect events artifact")
                content = message.get("content", [])
                final_answer = "\n".join(str(block.get("text", "")) for block in content if block.get("type") == "text")
    return {"commands": calls, "final_answer": final_answer}


def judge_checks(case_dir: Path, settings: JudgeSettings, evidence: dict[str, str],
                 dispatch: Dispatcher, output: Path) -> list[GradedCheck]:
    judge_path = case_dir / "judge.toml"
    if not judge_path.exists():
        return []
    judge = load_toml(judge_path, Judge)
    models = [settings.model, *([settings.second] if settings.second else [])]
    token = dispatch.register(models, 0.25, output / f"judge-usage-{uuid.uuid4().hex}.jsonl")
    checks: list[GradedCheck] = []
    records: list[dict[str, Any]] = []
    try:
        for question in judge.question:
            state = {name: evidence[name] for name in question.evidence}
            answers: list[bool | None] = []
            for model in models:
                response = dispatch.judge(token, {"model": model, "state": state,
                    "questions": {question.id: {"type": "noul", "instructions": question.text}}})
                try:
                    probability = NativeJudgment.model_validate(response).answers[question.id].noul
                except (ValidationError, KeyError):
                    raise ValueError("invalid native judge response") from None
                verdict = judge_verdict(probability, settings.pass_threshold, settings.fail)
                answers.append(verdict)
                records.append({"question": question.id, "model": model, "probability": probability,
                                "passed": verdict, "response": response})
            disagreement = answers[0] != answers[1] if len(answers) > 1 else None
            checks.append(GradedCheck(id=question.id, passed=answers[0], critical=question.critical,
                source="judge", targets=question.targets, evidence="judge.json", disagreement=disagreement))
        (output / "judge.json").write_text(json.dumps(records, indent=2) + "\n")
    finally:
        dispatch.revoke(token)
    return checks
