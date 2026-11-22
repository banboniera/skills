"""Tests for trial.py: python3 -m unittest discover -s <this dir>."""

import json
import shutil
import tempfile
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
            rule = write(root / "omp/rules/no-any.md", "x")
            command = write(root / ".omp/commands/verify.md", "x")
            self.assertEqual(trial.target_kind(skill), ("skill", "pdf"))
            self.assertEqual(trial.target_kind(skill / "SKILL.md"), ("skill", "pdf"))
            self.assertEqual(trial.target_kind(rule), ("rule", "no-any"))
            self.assertEqual(trial.target_kind(command), ("command", "verify"))
            with self.assertRaises(SystemExit):
                trial.target_kind(write(root / "notes/x.md", "x"))

    def test_skill_name_comes_from_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            skill = write(Path(d) / "dir/SKILL.md", "---\nname: real-name\ndescription: x\n---\n").parent
            self.assertEqual(trial.target_kind(skill), ("skill", "real-name"))


class Install(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.work = root / "work"
        self.work.mkdir()
        self.arm_dir = root / "arm"
        self.user_skills = root / "user-skills"
        write(self.user_skills / "pdf/SKILL.md", "user copy")
        write(self.user_skills / "other/SKILL.md", "other")
        self.source = root / "source"
        write(self.source / "SKILL.md", "arm copy")
        self.base = {"customDirectories": ["/existing"], "disabledExtensions": ["skill:old"]}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def install(self, kind: str, name: str, source: Path | None) -> dict:
        return trial.install(kind, name, source, self.work, self.arm_dir, self.user_skills, self.base)

    def test_skill_arm_replaces_user_copy_and_keeps_other_skills(self) -> None:
        write(self.work / ".agents/skills/pdf/SKILL.md", "fixture copy")
        overlay = self.install("skill", "pdf", self.source)
        mirror = self.arm_dir / "skills"
        self.assertEqual((mirror / "pdf/SKILL.md").read_text(), "arm copy")
        self.assertFalse((mirror / "pdf").is_symlink(), "the arm copy is a copy, so a trial cannot edit the source")
        self.assertEqual((mirror / "other").resolve(), (self.user_skills / "other").resolve())
        self.assertFalse((self.work / ".agents/skills/pdf").exists())
        self.assertEqual(overlay["skills"], {"enablePiUser": False, "customDirectories": [str(mirror), "/existing"]})

    def test_skill_without_arm_has_no_copy(self) -> None:
        self.install("skill", "pdf", None)
        self.assertFalse((self.arm_dir / "skills/pdf").exists())
        self.assertTrue((self.arm_dir / "skills/other").exists())

    def test_rule_arms(self) -> None:
        rule = write(Path(self.tmp.name) / "r.md", "---\ndescription: d\n---\nbody")
        write(self.work / ".omp/rules/no-any.mdc", "fixture copy")
        self.install("rule", "no-any", rule)
        self.assertEqual((self.work / ".omp/rules/no-any.md").read_text(), rule.read_text())
        self.assertFalse((self.work / ".omp/rules/no-any.mdc").exists())
        self.install("rule", "no-any", None)
        shadow = (self.work / ".omp/rules/no-any.md").read_text()
        self.assertFalse(shadow.startswith("---"), "the shadow has no frontmatter, so it never loads")

    def test_command_arms(self) -> None:
        command = write(Path(self.tmp.name) / "c.md", "Run $1")
        self.assertNotIn("disabledExtensions", self.install("command", "verify", command))
        self.assertEqual((self.work / ".omp/commands/verify.md").read_text(), "Run $1")
        overlay = self.install("command", "verify", None)
        self.assertFalse((self.work / ".omp/commands/verify.md").exists())
        self.assertEqual(overlay["disabledExtensions"], ["skill:old", "slash-command:verify"])

    def test_shadowed_reference_rules(self) -> None:
        trial.install("skill", "pdf", None, self.work, self.arm_dir, self.user_skills, self.base, shadow_rules=["guidance-edits"])
        self.assertEqual((self.work / ".omp/rules/guidance-edits.md").read_text(), trial.SHADOW)


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


class Overlay(unittest.TestCase):
    def test_trial_settings(self) -> None:
        overlay = trial.trial_overlay({}, advisor=False)
        self.assertEqual(overlay["memory"], {"backend": "off"})
        self.assertEqual(overlay["retry"], {"modelFallback": False, "usageAwareFallback": False})
        self.assertEqual(overlay["advisor"], {"enabled": False})
        self.assertNotIn("advisor", trial.trial_overlay({}, advisor=True))


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
                assistant([{"type": "text", "text": "Draft"}, call("bash", command="ls")], 0.25, 50),
                assistant([{"type": "text", "text": "Done."}], 0.25, 50),
            ])
            jsonl(session / "sub/child.jsonl", [assistant([call("read", "d", path="skill://other")], 1.0, 10), result("d")])
            m = trial.session_metrics(session, prompt="/verify src")
            self.assertEqual(m["cost"], 2.0)
            self.assertEqual(m["tokens"]["input"], 210)
            self.assertEqual(m["tool_calls"], {"read": 4, "bash": 1})
            self.assertEqual(m["turns"], 3)
            self.assertEqual(m["loads"], {"skills": ["other", "pdf"], "rules": ["guidance-edits", "no-any"], "command_expanded": True})
            self.assertEqual(m["final"], "Done.")


class Hint(unittest.TestCase):
    def test_short_description_is_shown_verbatim(self) -> None:
        self.assertEqual(trial.preview("  Use for  PDFs. "), "Use for PDFs.")

    def test_long_description_preview_cuts_at_a_sentence_or_word(self) -> None:
        sentence = "Writes Vitest tests for units and components in this repo. " + "x " * 60
        self.assertEqual(trial.preview(sentence), "Writes Vitest tests for units and components in this repo.")
        words = "word " * 40
        cut = trial.preview(words)
        self.assertTrue(cut.endswith("…") and len(cut) <= 100 and not cut.endswith(" …"))


class TtsrCases(unittest.TestCase):
    def test_verdicts(self) -> None:
        fired = {"triggered": [{"name": "r"}], "notTriggered": []}
        quiet = {"triggered": [], "notTriggered": [{"name": "r"}]}
        judged = {"triggered": [], "notTriggered": [{"name": "r", "question": "Q?"}]}
        self.assertEqual(trial.ttsr_verdict(fired), "fires")
        self.assertEqual(trial.ttsr_verdict(quiet), "quiet")
        self.assertEqual(trial.ttsr_verdict(judged), "question")


class References(unittest.TestCase):
    def test_lists_guidance_that_points_at_the_target(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            agent = Path(d)
            target = write(agent / "skills/pdf/SKILL.md", "see skill://pdf/x.md").parent
            write(agent / "rules/r.md", "Read `skill://pdf/writing.md` first.")
            write(agent / "commands/c.md", "Use skill://pdfx instead.")
            write(agent / "RULES.md", "Read rule://pdf when unsure.")
            found = trial.references("pdf", target, agent)
            self.assertEqual(sorted(p.name for p in found), ["RULES.md", "r.md"])


if __name__ == "__main__":
    unittest.main()
