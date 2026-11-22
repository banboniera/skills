"""Tests for trial.py: python3 -m unittest discover -s <this dir>."""

import argparse
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

import trial


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def assistant(content: list[dict], cost: float = 0.0, tokens: int = 0) -> dict:
    usage = {"input": tokens, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": tokens, "cost": {"total": cost}}
    return {"type": "message", "message": {"role": "assistant", "content": content, "usage": usage}}


def call(name: str, call_id: str = "", **args: str) -> dict:
    return {"type": "toolCall", "id": call_id, "name": name, "arguments": args}


def result(call_id: str, error: bool = False) -> dict:
    return {"type": "message", "message": {"role": "toolResult", "toolCallId": call_id, "isError": error, "content": []}}


class TargetKind(unittest.TestCase):
    def test_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skill = write(root / "skills/pdf/SKILL.md", "---\nname: pdf\n---\n").parent
            self.assertEqual(trial.target_kind(skill), ("skill", "pdf"))
            self.assertEqual(trial.target_kind(skill / "SKILL.md"), ("skill", "pdf"))
            self.assertEqual(trial.target_kind(write(root / "omp/rules/no-any.md", "x")), ("rule", "no-any"))
            self.assertEqual(trial.target_kind(write(root / ".omp/commands/verify.md", "x")), ("command", "verify"))
            self.assertEqual(trial.target_kind(write(root / "dir/SKILL.md", "---\nname: real-name\n---\n").parent), ("skill", "real-name"))
            with self.assertRaises(SystemExit):
                trial.target_kind(write(root / "notes/x.md", "x"))

    def test_triggered_rule(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(trial.is_triggered_rule(write(Path(d) / "a.md", "---\ncondition:\n  - 'x'\n---\nbody")))
            self.assertTrue(trial.is_triggered_rule(write(Path(d) / "b.md", "---\nquestion: Is it?\n---\nbody")))
            self.assertFalse(trial.is_triggered_rule(write(Path(d) / "c.md", "---\ndescription: d\n---\ncondition: in body")))


class ArmSource(unittest.TestCase):
    def test_with_arm_is_frozen_when_the_invocation_starts(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            target = write(Path(d) / "skills/pdf/SKILL.md", "v1").parent
            frozen = trial.arm_source("with", target, Path(d) / "arms")
            assert frozen is not None
            (target / "SKILL.md").write_text("v2")
            self.assertEqual((frozen / "SKILL.md").read_text(), "v1")


class Install(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.work = root / "work"
        self.work.mkdir()
        self.arm_dir = root / "arm"
        self.user_skills = root / "user-skills"
        for skill in ("pdf", "other", "linker"):
            write(self.user_skills / skill / "SKILL.md", skill)
        self.source = write(root / "source/SKILL.md", "arm copy").parent
        self.base = {"customDirectories": ["/existing"], "disabledExtensions": ["skill:old"], "disabledRules": ["r0"]}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def install(self, kind: str, name: str, source: Path | None, **hide: tuple[str, ...]) -> dict:
        return trial.install(kind, name, source, self.work, self.arm_dir, self.user_skills, self.base, **hide)

    def test_skill_arm_replaces_the_user_copy_and_keeps_other_skills(self) -> None:
        write(self.work / ".agents/skills/pdf/SKILL.md", "fixture copy")
        overlay = self.install("skill", "pdf", self.source)
        mirror = self.arm_dir / "skills"
        self.assertEqual((mirror / "pdf/SKILL.md").read_text(), "arm copy")
        self.assertEqual((mirror / "other").resolve(), (self.user_skills / "other").resolve())
        self.assertFalse((self.work / ".agents/skills/pdf").exists())
        self.assertEqual(overlay["skills"], {"enablePiUser": False, "customDirectories": [str(mirror), "/existing"]})
        self.assertNotIn("disabledExtensions", overlay)

    def test_skill_without_arm_disables_it_everywhere_and_hides_linking_guidance(self) -> None:
        overlay = self.install("skill", "pdf", None, hide_skills=("linker",), hide_rules=("points-at-pdf",))
        self.assertFalse((self.arm_dir / "skills/pdf").exists())
        self.assertFalse((self.arm_dir / "skills/linker").exists())
        self.assertTrue((self.arm_dir / "skills/other").exists())
        self.assertEqual(overlay["disabledExtensions"], ["skill:old", "skill:pdf"])
        self.assertEqual(overlay["ttsr"], {"disabledRules": ["r0", "points-at-pdf"]})

    def test_rule_arms(self) -> None:
        rule = write(Path(self.tmp.name) / "r.md", "---\ndescription: d\n---\nbody")
        write(self.work / ".omp/rules/no-any.mdc", "fixture copy")
        self.assertNotIn("ttsr", self.install("rule", "no-any", rule))
        self.assertEqual((self.work / ".omp/rules/no-any.md").read_text(), rule.read_text())
        self.assertFalse((self.work / ".omp/rules/no-any.mdc").exists())
        overlay = self.install("rule", "no-any", None)
        self.assertFalse((self.work / ".omp/rules/no-any.md").exists(), "no file an agent could read")
        self.assertEqual(overlay["ttsr"], {"disabledRules": ["r0", "no-any"]})

    def test_command_arms(self) -> None:
        command = write(Path(self.tmp.name) / "c.md", "Run $1")
        self.assertNotIn("disabledExtensions", self.install("command", "verify", command))
        self.assertEqual((self.work / ".omp/commands/verify.md").read_text(), "Run $1")
        overlay = self.install("command", "verify", None)
        self.assertFalse((self.work / ".omp/commands/verify.md").exists())
        self.assertEqual(overlay["disabledExtensions"], ["skill:old", "slash-command:verify"])

    def test_every_arm_turns_the_users_mcp_servers_off(self) -> None:
        write(self.work / ".omp/mcp.json", json.dumps({"mcpServers": {"fixture-db": {"command": "db"}}}))
        trial.install("command", "verify", None, self.work, self.arm_dir, self.user_skills, {**self.base, "mcpServers": ["linear"]})
        servers = json.loads((self.work / ".omp/mcp.json").read_text())["mcpServers"]
        self.assertEqual(servers, {"fixture-db": {"command": "db"}, "linear": {"enabled": False}})


class Overlay(unittest.TestCase):
    def test_trial_settings(self) -> None:
        overlay = trial.trial_overlay({}, advisor=False)
        self.assertEqual(overlay["memory"], {"backend": "off"})
        self.assertEqual(overlay["retry"], {"modelFallback": False, "usageAwareFallback": False})
        self.assertEqual(overlay["computer"], {"enabled": False})
        self.assertEqual(overlay["archive"], {"enabled": False}, "past sessions would show a without arm the target's work")
        self.assertEqual(overlay["advisor"], {"enabled": False})
        self.assertNotIn("advisor", trial.trial_overlay({}, advisor=True))

    def test_trial_sessions_carry_the_nested_trial_marker(self) -> None:
        self.assertEqual(trial.trial_env(Path("/o.json"))["OMP_TRIAL"], "1")


class Diff(unittest.TestCase):
    def test_diff_shows_the_agents_changes_but_not_the_arm(self) -> None:
        work, _ = trial.prepare_work(None, None)
        try:
            write(work / ".omp/rules/no-any.md", "arm copy")
            base = trial.commit_all(work, "arm")
            write(work / ".omp/rules/added-by-agent.md", "agent rule")
            write(work / ".omp/rules/no-any.md", "edited by agent")
            diff = trial.changes(work, base)
            self.assertIn("added-by-agent.md", diff)
            self.assertIn("+edited by agent", diff)
            self.assertNotIn("+arm copy", diff)
        finally:
            shutil.rmtree(work.parent)

    def test_a_real_repository_fixture_copies_only_tracked_files_at_the_revision(self) -> None:
        repo, _ = trial.prepare_work(None, None)
        try:
            write(repo / "src/app.py", "v1")
            rev = trial.commit_all(repo, "v1")
            write(repo / "src/app.py", "v2")
            write(repo / ".env", "SECRET=1")
            work, _ = trial.prepare_work(None, None, repo=str(repo), rev=rev)
            try:
                self.assertEqual((work / "src/app.py").read_text(), "v1")
                self.assertFalse((work / ".env").exists())
            finally:
                shutil.rmtree(work.parent)
        finally:
            shutil.rmtree(repo.parent)


class Guard(unittest.TestCase):
    def test_sees_a_second_edit_of_an_already_modified_file_and_files_behind_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            repo, _ = trial.prepare_work(None, None)
            try:
                write(repo / "a.md", "one")
                trial.commit_all(repo, "a")
                write(repo / "a.md", "two")
                linked = write(Path(d) / "real/skill/SKILL.md", "x").parent
                agent = Path(d) / "agent"
                agent.mkdir()
                (agent / "skill").symlink_to(linked)
                before = trial.guard_snapshot([repo, agent])
                write(repo / "a.md", "three")
                self.assertNotEqual(before, trial.guard_snapshot([repo, agent]))
                after_repo = trial.guard_snapshot([repo, agent])
                write(linked / "SKILL.md", "changed!")
                self.assertNotEqual(after_repo, trial.guard_snapshot([repo, agent]))
            finally:
                shutil.rmtree(repo.parent)


class Session(unittest.TestCase):
    def test_metrics_and_final_answer(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            session = Path(d)
            jsonl(session / "2026_main.jsonl", [
                {"type": "session"},
                {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "expanded body"}]}},
                assistant([call("read", "a", path="skill://pdf/refs.md"), call("read", "b", path="rule://no-any"),
                           call("read", "c", path="skill://gone")], 0.5, 100),
                result("a"), result("b"), result("c", error=True),
                {"type": "ttsr_injection", "injectedRules": ["guidance-edits"]},
                {"type": "model_usage", "purpose": "ttsr", "usage": {"cost": {"total": 0.125}}},
                assistant([{"type": "text", "text": "Draft"}, call("bash", command="ls")], 0.25, 50),
                assistant([{"type": "text", "text": "Done."}], 0.25, 50),
            ])
            jsonl(session / "sub/child.jsonl", [assistant([call("read", "d", path="skill://other")], 1.0, 10), result("d")])
            m = trial.session_metrics(session, prompt="/verify src")
            self.assertEqual(m["cost"], 2.125)
            self.assertEqual(m["tokens"]["input"], 210)
            self.assertEqual(m["tool_calls"], {"read": 4, "bash": 1})
            self.assertEqual(m["turns"], 3)
            self.assertEqual(m["loads"], {"skills": ["other", "pdf"], "rules": ["guidance-edits", "no-any"], "command_expanded": True})
            self.assertEqual(m["final"], "Done.")
            self.assertFalse(m["touched_target"])

    def test_touching_the_target_by_path_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            markers = trial.target_markers("skill", "pdf", Path(d) / "repo/skills/pdf")
            jsonl(Path(d) / "s/main.jsonl", [assistant([call("bash", command="cat ~/.omp/agent/skills/pdf/SKILL.md")])])
            self.assertTrue(trial.session_metrics(Path(d) / "s", "x", markers)["touched_target"])
            jsonl(Path(d) / "t/main.jsonl", [assistant([call("bash", command="cat skills/pdf-forms/SKILL.md")])])
            self.assertFalse(trial.session_metrics(Path(d) / "t", "x", markers)["touched_target"])


class Hint(unittest.TestCase):
    def test_short_description_is_shown_verbatim(self) -> None:
        self.assertEqual(trial.preview("  Use for  PDFs. "), "Use for PDFs.")

    def test_long_description_preview_cuts_at_a_sentence_or_word(self) -> None:
        sentence = "Writes Vitest tests for units and components in this repo. " + "x " * 60
        self.assertEqual(trial.preview(sentence), "Writes Vitest tests for units and components in this repo.")
        cut = trial.preview("word " * 40)
        self.assertTrue(cut.endswith("…") and len(cut) <= 100 and not cut.endswith(" …"))


class Budget(unittest.TestCase):
    def runner(self, d: str, out: str, budget: float, max_cost: float = 3.0) -> trial.Runner:
        target = write(Path(d) / "skills/pdf/SKILL.md", "---\nname: pdf\n---\n").parent
        return trial.Runner(argparse.Namespace(target=target, budget=budget, max_cost=max_cost), Path(d) / "ws/pdf" / out)

    def test_budget_covers_every_iteration_of_a_target(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            first = self.runner(d, "iteration-1", 1.0)
            cap = first.admit()
            self.assertEqual(cap, 1.0)
            first.charge(0.75, 1.0)
            second = self.runner(d, "iteration-2", 1.0)
            cap = second.admit()
            self.assertEqual(cap, 0.25)
            second.charge(0.25, 0.25)
            self.assertIsNone(second.admit())
            self.assertIsNone(self.runner(d, "iteration-3", 1.0).admit())
            self.assertIsNotNone(self.runner(d, "iteration-3", 2.0).admit())

    def test_runs_in_flight_reserve_their_cap(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            runner = self.runner(d, "iteration-1", 5.0, max_cost=2.0)
            self.assertEqual([runner.admit(), runner.admit(), runner.admit(), runner.admit()], [2.0, 2.0, 1.0, None])

    def test_concurrent_admits_never_reserve_past_the_budget(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            runner = self.runner(d, "iteration-1", 3.0, max_cost=1.0)
            caps: list[float | None] = []
            threads = [threading.Thread(target=lambda: caps.append(runner.admit())) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(sum(c for c in caps if c), 3.0)


class TtsrCases(unittest.TestCase):
    def test_verdicts(self) -> None:
        self.assertEqual(trial.ttsr_verdict({"triggered": [{"name": "r"}], "notTriggered": []}), "fires")
        self.assertEqual(trial.ttsr_verdict({"triggered": [], "notTriggered": [{"name": "r"}]}), "quiet")
        judged = {"name": "r", "question": "Q?", "defined": {"regex": ["x"], "ast": []}}
        self.assertEqual(trial.ttsr_verdict({"triggered": [], "notTriggered": [{**judged, "matched": {"regex": ["x"], "ast": []}}]}), "question")
        self.assertEqual(trial.ttsr_verdict({"triggered": [], "notTriggered": [{**judged, "matched": {"regex": [], "ast": []}}]}), "quiet")


class References(unittest.TestCase):
    def test_lists_guidance_that_links_to_the_target_and_its_owner(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            agent = Path(d)
            target = write(agent / "skills/pdf/SKILL.md", "see skill://pdf/x.md").parent
            write(agent / "skills/linker/notes.md", "Read `skill://pdf/writing.md` first.")
            write(agent / "rules/r.md", "Read rule://pdf when unsure.")
            write(agent / "commands/c.md", "Use skill://pdfx instead.")
            found = trial.references("pdf", target, agent)
            self.assertEqual(sorted(trial.owner(p, agent) for p in found), [("rule", "r"), ("skill", "linker")])


class Durations(unittest.TestCase):
    def test_durations(self) -> None:
        self.assertEqual([trial.duration_seconds(t) for t in ("600", "15m", "1h")], [600, 900, 3600])


if __name__ == "__main__":
    unittest.main()
