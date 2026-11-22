"""Tests for grade.py: python3 -m unittest discover -s <this dir>."""

import asyncio
import json
import tempfile
import unittest
from collections.abc import AsyncIterator
from pathlib import Path

import grade


class FakeItem:
    def __init__(self, answers: dict) -> None:
        self.ok, self.answers, self.error = True, answers, None


class FakeBatch:
    def __init__(self, states: dict, questions: dict, answers: dict) -> None:
        self.items = [(k, FakeItem({q: {"type": "bool", "bool": answers[(k, questions[q]["instructions"])]} for q in questions}))
                      for k in states]

    async def drain_iter(self, timeout: float) -> AsyncIterator[tuple[str, FakeItem]]:
        for item in self.items:
            yield item


class FakeHandle:
    def __init__(self, value: dict) -> None:
        self.value = value

    async def wait(self) -> dict:
        return self.value


class Grade(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        runs = []
        for arm in ("without", "with"):
            d = self.out / "runs/e1" / f"{arm}-1"
            d.mkdir(parents=True)
            (d / "metrics.json").write_text(json.dumps({"arm": arm, "prompt": "Add a rule"}))
            (d / "final.md").write_text(f"answer {arm}")
            (d / "diff.patch").write_text("+rule")
            (d / "checks.json").write_text("[]")
            runs.append({"eval": "e1", "arm": arm, "rep": 1, "status": "done", "dir": f"runs/e1/{arm}-1"})
        runs.append({"eval": "e1", "arm": "with", "rep": 2, "status": "skipped: budget"})
        index = {"name": "pdf-forms", "evals": {"e1": {"prompt": "Add a rule", "expectations": ["names the file", "cites evidence"]}}, "runs": runs}
        (self.out / "index.json").write_text(json.dumps(index))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_state_hides_the_arm(self) -> None:
        state = grade.state(self.out / "runs/e1/with-1", "pdf-forms")
        self.assertEqual(set(state), {"task", "final_answer", "changes", "checks"})
        self.assertNotIn("with", json.dumps(state).replace("answer with", ""))

    def test_state_masks_the_target_name_and_lockfile_noise(self) -> None:
        d = self.out / "runs/e1/with-1"
        (d / "final.md").write_text("Using the PDF-Forms skill, I fixed it.")
        lock = "diff --git a/package-lock.json b/package-lock.json\n" + "+x\n" * 50_000
        (d / "diff.patch").write_text(lock + "diff --git a/src/a.ts b/src/a.ts\n+fixed\n")
        state = grade.state(d, "pdf-forms")
        self.assertEqual(state["final_answer"], "Using the [the guidance] skill, I fixed it.")
        self.assertIn("+fixed", state["changes"])
        self.assertIn("package-lock.json", state["changes"])
        self.assertLess(len(state["changes"]), 1000)

    def test_judge_verdicts_and_second_opinion_for_uncertain_ones(self) -> None:
        answers = {}
        for arm, p in (("without", (0.1, 0.5)), ("with", (0.9, 0.95))):
            key = f"runs/e1/{arm}-1"
            answers[(key, grade.question("names the file")["instructions"])] = p[0]
            answers[(key, grade.question("cites evidence")["instructions"])] = p[1]
        second: list[str] = []

        def judge_batch(states: dict, questions: dict, intent: str) -> FakeBatch:
            return FakeBatch(states, questions, answers)

        def completion(prompt: str, model: str, system: str, schema: dict) -> FakeHandle:
            second.append(prompt)
            if "weak" in schema["properties"]:
                return FakeHandle({"weak": [], "missing": ["no check that the rule loads"]})
            return FakeHandle({"passed": True, "evidence": "line 3 names it"})

        asyncio.run(grade.grade(self.out, judge_batch, completion))
        without = json.loads((self.out / "runs/e1/without-1/grading.json").read_text())["expectations"]
        self.assertEqual([(g["text"], g["passed"]) for g in without], [("names the file", False), ("cites evidence", True)])
        self.assertEqual(without[1]["evidence"], "line 3 names it")
        opinions = [json.loads(p)["expectation"] for p in second if "expectation" in json.loads(p)]
        self.assertEqual(opinions, ["cites evidence"], "only the uncertain verdict gets a second opinion")
        feedback = json.loads((self.out / "eval_feedback.json").read_text())
        self.assertEqual(feedback["e1"]["missing"], ["no check that the rule loads"])


if __name__ == "__main__":
    unittest.main()
