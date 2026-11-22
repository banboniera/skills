"""Tests for report.py: python3 -m unittest discover -s <this dir>."""

import json
import tempfile
import unittest
from pathlib import Path

import report


def make_run(out: Path, ev: str, arm: str, rep: int, expectations: list[bool], checks: list[bool], loads: dict, cost: float) -> dict:
    run = out / "runs" / ev / f"{arm}-{rep}"
    run.mkdir(parents=True)
    (run / "metrics.json").write_text(json.dumps({"eval": ev, "arm": arm, "rep": rep, "cost": cost, "seconds": 10.0, "exit_code": 0,
                                                  "tokens": {"input": 100, "output": 10, "cacheRead": 0, "cacheWrite": 0},
                                                  "tool_calls": {"read": 2}, "turns": 2, "loads": loads, "prompt": "do <it>"}))
    (run / "checks.json").write_text(json.dumps([{"name": f"c{i}", "passed": p, "exit_code": 0 if p else 1, "output": ""} for i, p in enumerate(checks)]))
    (run / "grading.json").write_text(json.dumps({"expectations": [{"text": f"x{i}", "passed": p, "p_yes": 1.0 if p else 0.0, "evidence": ""}
                                                                   for i, p in enumerate(expectations)]}))
    (run / "final.md").write_text("<b>answer</b>")
    (run / "diff.patch").write_text("")
    return {"eval": ev, "arm": arm, "rep": rep, "status": "done", "dir": str(run.relative_to(out))}


class Stats(unittest.TestCase):
    def test_mean_and_sample_stddev(self) -> None:
        self.assertEqual(report.stats([]), {"mean": None, "stddev": None, "n": 0})
        self.assertEqual(report.stats([0.5]), {"mean": 0.5, "stddev": 0.0, "n": 1})
        s = report.stats([1.0, 0.0, 1.0, 0.0])
        self.assertEqual(s["mean"], 0.5)
        self.assertAlmostEqual(s["stddev"], 0.57735, places=4)


class Benchmark(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        loaded = {"skills": ["pdf"], "rules": [], "command_expanded": False}
        none = {"skills": [], "rules": [], "command_expanded": False}
        runs = [
            make_run(self.out, "e1", "without", 1, [False, True], [False], none, 1.0),
            make_run(self.out, "e1", "without", 2, [False, True], [True], none, 2.0),
            make_run(self.out, "e1", "with", 1, [True, True], [True], loaded, 3.0),
            make_run(self.out, "e1", "with", 2, [True, True], [True], none, 3.0),
            {"eval": "e1", "arm": "with", "rep": 3, "status": "skipped: budget"},
        ]
        index = {"target": "/x/pdf", "kind": "skill", "name": "pdf", "arms": ["without", "with"], "model": None,
                 "evals": {"e1": {"prompt": "p", "baseline_prompt": None, "expectations": ["x0", "x1"]}}, "runs": runs, "spent": 9.0, "stopped": ""}
        (self.out / "index.json").write_text(json.dumps(index))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_arm_summary(self) -> None:
        b = report.benchmark(self.out)
        without, with_ = b["arms"]["without"], b["arms"]["with"]
        self.assertEqual(without["expectations"]["mean"], 0.5)
        self.assertEqual(with_["expectations"]["mean"], 1.0)
        self.assertEqual(without["checks"]["mean"], 0.5)
        self.assertEqual(with_["cost"]["mean"], 3.0)
        self.assertEqual(with_["loaded"], 0.5)
        self.assertEqual(with_["runs"], 2)
        self.assertEqual(b["skipped"], 1)

    def test_flags_name_items_that_do_not_discriminate(self) -> None:
        flags = {(f["eval"], f["kind"], f["name"]): f["flag"] for f in report.benchmark(self.out)["items"]}
        self.assertEqual(flags[("e1", "expectation", "x1")], "same in every arm")
        self.assertIsNone(flags[("e1", "expectation", "x0")])

    def test_flag_rules(self) -> None:
        self.assertIsNone(report.flag({"without": [True, False, False], "with": [True, True, True]}), "with clearly ahead")
        self.assertEqual(report.flag({"without": [True, False], "with": [False, True]}), "varies within an arm")
        self.assertEqual(report.flag({"with": [False, False, False]}), "never passes")
        self.assertEqual(report.flag({"without": [True, True], "with": [True, True]}), "same in every arm")

    def test_spread_is_across_reps_not_across_evals(self) -> None:
        none = {"skills": [], "rules": [], "command_expanded": False}
        runs = [make_run(self.out, ev, "with", rep, [ev == "easy"], [], none, 1.0) for ev in ("easy", "hard") for rep in (1, 2, 3)]
        index = {"target": "/x", "kind": "skill", "name": "pdf", "arms": ["with"], "model": None,
                 "evals": {e: {"prompt": "p", "expectations": ["x0"]} for e in ("easy", "hard")}, "runs": runs, "spent": 6.0, "stopped": ""}
        (self.out / "index.json").write_text(json.dumps(index))
        self.assertEqual(report.benchmark(self.out)["arms"]["with"]["expectations"], {"mean": 0.5, "stddev": 0.0, "n": 3})

    def test_delta_against_previous_iteration(self) -> None:
        current = report.benchmark(self.out)
        previous = json.loads(json.dumps(current))
        previous["arms"]["with"]["expectations"]["mean"] = 0.75
        self.assertEqual(report.deltas(current, previous)["with"]["expectations"], 0.25)

    def test_html_escapes_agent_output(self) -> None:
        page = report.html(report.benchmark(self.out), self.out, None)
        self.assertIn("&lt;b&gt;answer&lt;/b&gt;", page)
        self.assertNotIn("<b>answer</b>", page)
        self.assertIn("do &lt;it&gt;", page)


if __name__ == "__main__":
    unittest.main()
