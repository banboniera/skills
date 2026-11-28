"""Tests for trial.py: python3 -m unittest discover -s <this dir>."""

import argparse
import contextlib
import hashlib
import io
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.assertEqual(overlay.get("lsp"), {"enabled": False})
        self.assertEqual(trial.trial_overlay({}, advisor=False, lsp=True)["lsp"], {"enabled": True})
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
            self.assertEqual(trial.git(work, "diff", "--cached"), "")
            self.assertIn("+edited by agent", trial.git(work, "diff"))
            self.assertIn("+edited by agent", trial.git(work, "diff", "HEAD"))
            self.assertIn("?? .omp/rules/added-by-agent.md", trial.git(work, "status", "--porcelain"))
        finally:
            shutil.rmtree(work.parent)

    def test_diff_does_not_replace_the_agents_staged_content(self) -> None:
        work, base = trial.prepare_work(None, None)
        try:
            write(work / "artifact", "staged\n")
            trial.git(work, "add", "artifact")
            write(work / "artifact", "unstaged\n")
            self.assertIn("+unstaged", trial.changes(work, base))
            self.assertEqual(trial.git(work, "show", ":artifact"), "staged\n")
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


class RunCLI(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.agent = self.root / "agent"
        self.repo = self.root / "repo"
        self.target = write(self.repo / ".omp/commands/example.md", "Example")
        trial.git(self.repo, "init", "-q")
        trial.commit_all(self.repo, "target")
        self.out = self.root / "output/iteration-1"
        self.evals = self.root / "evals.json"
        env = f"#!{sys.executable}\n"
        omp = write(self.root / "bin/omp", env + """\
import json
import os
import sqlite3
import sys
from pathlib import Path

if sys.argv[1] == "config":
    print('{"value": null}')
elif sys.argv[1] == "ttsr":
    print('[{"name": "example", "path": "/wrong/example.md"}]')
elif sys.argv[1] == "skill":
    overlay = json.loads(Path(os.environ["PI_CONFIG_FILES"].split(os.pathsep)[-1]).read_text())
    skills = []
    if not os.getenv("DROP_SKILL"):
        for directory in overlay.get("skills", {}).get("customDirectories", []):
            skills.extend({"name": p.parent.name, "filePath": str(p)} for p in Path(directory).glob("*/SKILL.md"))
    print(json.dumps({"skills": skills}))
elif "--mode" in sys.argv and sys.argv[sys.argv.index("--mode") + 1] == "rpc":
    request = json.load(sys.stdin)
    capture = Path(sys.argv[sys.argv.index("--session-dir") + 1])
    if os.getenv("WRONG_CAPTURE"):
        capture = Path(os.environ["PI_CODING_AGENT_DIR"]) / "sessions"
    print(json.dumps({"id": request["id"], "type": "response", "command": request["type"],
                      "success": True, "data": {"sessionFile": str(capture / "trial.jsonl"), "model": {"id": "test"}}}))
else:
    overlay = Path(os.environ["PI_CONFIG_FILES"].split(os.pathsep)[-1])
    observed = {k: os.getenv(k) for k in ("TOP", "LOCAL", "SHARED")}
    observed["lsp"] = json.loads(overlay.read_text()).get("lsp")
    Path("tracked").write_text(json.dumps(observed) + "\\n")
    Path("untracked").write_text("new file")
    if os.getenv("TEST_PROFILE"):
        profile = Path(os.environ["PI_CODING_AGENT_DIR"])
        assert profile.stat().st_mode & 0o777 == 0o700
        assert (profile / "sessions/sample.jsonl").is_file()
        assert not (profile / "sessions/canary.jsonl").exists()
        assert (profile / "config.yml").read_text() == "original config"
        (profile / "config.yml").write_text("changed config")
        with sqlite3.connect(profile / "agent.db") as conn:
            assert list(conn.execute("SELECT item FROM fixture")) == [("original auth",)]
            conn.execute("INSERT INTO fixture VALUES ('new auth')")
        (profile / "extensions/example.ts").write_text("changed extension")
        Path("profile_path").write_text(str(profile))
""")
        omp.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{omp.parent}{os.pathsep}{os.environ['PATH']}",
                    "PI_CODING_AGENT_DIR": str(self.agent)}
        self.env.pop("OMP_TRIAL", None)
        self.env.pop("OMP_PROFILE", None)
        self.env.pop("PI_PROFILE", None)

    def cli(self, data: dict, *options: str, command: str = "run", out: Path | None = None,
            arms: tuple[str, ...] = ("with",)) -> subprocess.CompletedProcess:
        self.evals.write_text(json.dumps(data))
        return subprocess.run(
            [sys.executable, trial.__file__, command, "--target", str(self.target), "--evals", str(self.evals),
             "--out", str(out or self.out), "--reps", "1", "--budget", "3",
             *(part for arm in arms for part in ("--arm", arm)), *options],
            env=self.env, capture_output=True, text=True,
        )

    def test_dry_run_fails_isolation(self) -> None:
        self.target = write(self.repo / ".omp/rules/example.md", "---\ncondition: x\n---\n")
        res = self.cli({"evals": [{"id": "one", "prompt": "go"}]}, "--dry-run")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("isolation failed", res.stdout)

    def test_refuses_output_in_a_guarded_tree_before_creating_artifacts(self) -> None:
        linked = self.root / "linked-skill"
        linked.mkdir()
        (self.agent / "skills").mkdir(parents=True)
        (self.agent / "skills/link").symlink_to(linked)
        for parent in (self.repo, self.agent / "rules", linked):
            with self.subTest(parent=parent):
                out = parent / "trials/iteration-1"
                res = self.cli({"evals": [{"id": "one", "prompt": "go"}]}, "--dry-run", out=out)
                self.assertNotEqual(res.returncode, 0, res.stdout)
                self.assertIn("--out", res.stderr)
                self.assertFalse(out.parent.exists())

    def test_refuses_output_in_a_guarded_tree_for_triggers_too(self) -> None:
        self.target = write(self.repo / ".omp/rules/example.md", "---\ndescription: example\n---\n")
        out = self.repo / "trials/iteration-1"
        res = self.cli({"triggers": [{"query": "go", "should_trigger": False}]}, command="triggers", out=out)
        self.assertNotEqual(res.returncode, 0, res.stdout)
        self.assertIn("--out", res.stderr)
        self.assertFalse(out.parent.exists())

    def test_run_selects_split_before_limit_and_defaults_to_all(self) -> None:
        data = {"evals": [{"id": k, "prompt": k, **fields} for k, fields in
                          (("implicit", {}), ("held", {"split": "test"}), ("explicit", {"split": "train"}))]}
        for flags, wanted in (([], ["implicit", "held", "explicit"]),
                              (["--split", "train"], ["implicit", "explicit"]),
                              (["--split", "test", "--limit", "1"], ["held"])):
            with self.subTest(flags=flags):
                res = self.cli(data, "--dry-run", *flags)
                self.assertEqual(res.returncode, 0, res.stderr)
                index = json.loads((self.out / "index.json").read_text())
                self.assertEqual(list(index["evals"]), wanted)

    def test_session_and_checks_see_merged_env_and_checks_see_unstaged_edits(self) -> None:
        patch_file = shlex.quote(str(self.out / "runs/one/with-1/diff.patch"))
        res = self.cli({
            "env": {"TOP": "top", "SHARED": "global"},
            "evals": [{
                "id": "one", "prompt": "go", "setup": "echo base >tracked",
                "env": {"LOCAL": "local", "SHARED": "eval"}, "lsp": True,
                "checks": [{"name": "evaluate real diff", "run": (
                    'test "$TOP:$LOCAL:$SHARED" = top:local:eval'
                    ' && git diff --exit-code --cached && ! git diff --quiet'
                    ' && test -n "$(git diff HEAD)"'
                    f' && grep -q "new file" {patch_file}'
                )}],
            }],
        })
        self.assertEqual(res.returncode, 0, res.stderr)
        run = self.out / "runs/one/with-1"
        self.assertEqual(json.loads((run / "checks.json").read_text())[0]["exit_code"], 0)
        addition = next(line[1:] for line in (run / "diff.patch").read_text().splitlines() if line.startswith("+{"))
        self.assertEqual(json.loads(addition), {"TOP": "top", "LOCAL": "local", "SHARED": "eval", "lsp": {"enabled": True}})

    def test_both_arms_and_checks_use_private_fixture_history(self) -> None:
        self.target = write(self.repo / "skills/example/SKILL.md", "---\nname: example\n---\n").parent
        original_config = write(self.root / "config.yml", "original config")
        self.agent.mkdir()
        (self.agent / "config.yml").symlink_to(original_config)
        extension = write(self.root / "extensions/example.ts", "original extension")
        (self.agent / "extensions").symlink_to(extension.parent)
        canary = write(self.agent / "sessions/canary.jsonl", "live session")
        db = self.agent / "agent.db"
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("CREATE TABLE fixture (item TEXT)")
            conn.execute("INSERT INTO fixture VALUES ('original auth')")
            conn.commit()
            paths = (original_config, db, Path(f"{db}-wal"), extension, canary)
            before = [hashlib.sha256(path.read_bytes()).digest() for path in paths]
            data = {"history": ".fixture-sessions", "env": {"TEST_PROFILE": "1"}, "evals": [{
                "id": "one", "prompt": "go",
                "setup": "mkdir .fixture-sessions && touch .fixture-sessions/sample.jsonl",
                "checks": [{"name": "uses same private profile", "run": (
                    'test "$PI_CODING_AGENT_DIR" = "$(cat profile_path)"'
                    ' && test -f "$PI_CODING_AGENT_DIR/sessions/sample.jsonl"'
                    ' && test ! -e "$PI_CODING_AGENT_DIR/sessions/canary.jsonl"'
                )}],
            }]}
            res = self.cli(data, "--keep", "--max-cost", "1", arms=("with", "without"))
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertEqual([hashlib.sha256(path.read_bytes()).digest() for path in paths], before)
            for arm in ("with", "without"):
                run = self.out / f"runs/one/{arm}-1"
                diff = (run / "diff.patch").read_text()
                profile = Path(next(line[1:] for line in diff.splitlines() if line.startswith("+/tmp/")))
                self.addCleanup(shutil.rmtree, profile.parent, ignore_errors=True)
                self.assertFalse(profile.exists())
                overlay = json.loads((run / "overlay.json").read_text())
                self.assertEqual(overlay["archive"], {"enabled": True})
                self.assertTrue(json.loads((run / "checks.json").read_text())[0]["passed"])

    def test_dry_run_checks_skill_discovery_and_session_capture_with_fixture_history(self) -> None:
        self.target = write(self.repo / "skills/example/SKILL.md", "---\nname: example\n---\n").parent
        for flag, problem in (("DROP_SKILL", "skill example: loads nothing"), ("WRONG_CAPTURE", "session capture")):
            with self.subTest(flag=flag):
                res = self.cli({"evals": [{"id": "one", "prompt": "go", "history": "history",
                                          "env": {flag: "1"}}]}, "--dry-run")
                self.assertEqual(res.returncode, 1)
                self.assertIn(problem, res.stdout + res.stderr)

    def test_fixture_history_refuses_named_profiles_in_dry_run(self) -> None:
        for variable in ("OMP_PROFILE", "PI_PROFILE"):
            with self.subTest(variable=variable):
                res = self.cli({"history": "history", "evals": [
                    {"id": "one", "prompt": "go", "env": {variable: "separate-profile"}},
                ]}, "--dry-run")
                self.assertEqual(res.returncode, 1)
                self.assertIn(f"unset {variable}", res.stdout + res.stderr)

    def test_empty_omp_profile_overrides_legacy_profile_for_fixture_history(self) -> None:
        self.env["PI_PROFILE"] = "separate-profile"
        res = self.cli({"history": "history", "env": {"OMP_PROFILE": ""},
                        "evals": [{"id": "one", "prompt": "go"}]}, "--dry-run")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_fixture_history_may_not_point_at_live_sessions(self) -> None:
        canary = write(self.agent / "sessions/canary.jsonl", "live session")
        res = self.cli({"evals": [{"id": "one", "prompt": "go", "history": "history",
                                  "setup": f"ln -s {shlex.quote(str(canary.parent))} history"}]}, "--dry-run")
        self.assertEqual(res.returncode, 1)
        self.assertIn("history must stay inside the trial copy", res.stdout + res.stderr)


class Setup(unittest.TestCase):
    def test_failed_setup_removes_its_trial_copy(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "omp-trial"
            root.mkdir()
            with patch.object(trial.tempfile, "mkdtemp", return_value=str(root)):
                with self.assertRaises(subprocess.CalledProcessError):
                    trial.prepare_work(None, "touch setup-started && exit 9")
            self.assertFalse(root.exists())


class TtsrCases(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.rule = write(self.root / "rules/example.md", "---\ncondition: token\n---\n")
        self.evals = self.root / "evals.json"

    def cases(self, *cases: dict) -> tuple[int | str, str]:
        self.evals.write_text(json.dumps({"rule_cases": cases}))
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
            trial.cmd_rules(argparse.Namespace(target=self.rule, evals=self.evals))
        return stopped.exception.code, output.getvalue()

    def result(self, *rules: str, fires: bool = False) -> subprocess.CompletedProcess:
        entries = [{"name": name, "matched": {"regex": ["token"]}} for name in rules]
        return subprocess.CompletedProcess([], 0, json.dumps({
            "triggered": entries if fires else [], "notTriggered": [] if fires else entries,
        }), "")

    def test_judged_rule_preserves_other_frontmatter_and_respects_scope(self) -> None:
        prefix = b"---\r\ncondition:\r\n  - token\r\n"
        suffix = b"\r\n# scope comment\r\nscope: 'tool:edit(src/*.rs)'\r\n---\r\nquestion: body\r\n"
        original = prefix + b"question: >-\r\n  line one\r\n  line two\r\n" + suffix
        self.rule.write_bytes(original)

        def ttsr(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
            isolated = Path(cmd[cmd.index("--rule") + 1])
            self.assertNotEqual(isolated, self.rule)
            self.assertEqual(isolated.read_bytes(), prefix + suffix)
            self.assertEqual(kwargs["input"], "token")
            return self.result("example", fires=cmd[cmd.index("--path") + 1] == "src/a.rs")

        with patch.object(trial.subprocess, "run", side_effect=ttsr):
            code, out = self.cases({"snippet": "token", "path": "docs/a.rs", "fires": False},
                                   {"snippet": "token", "path": "src/a.rs", "fires": True})
        self.assertEqual(code, 0, out)
        self.assertIn("scope+prefilter; judge not run", out)
        self.assertIn("got quiet", out)
        self.assertIn("got fires", out)
        self.assertEqual(self.rule.read_bytes(), original)

    def test_uses_only_a_verdict_from_exactly_the_intended_rule(self) -> None:
        for names in ((), ("another",), ("example", "second")):
            with self.subTest(names=names), patch.object(trial.subprocess, "run", return_value=self.result(*names)):
                code, out = self.cases({"snippet": "other", "path": "src/a.rs", "fires": False})
                self.assertNotEqual(code, 0)
                self.assertIn("exactly", str(code) + out)

    def test_cases_without_expectations_print_verdicts_without_failing(self) -> None:
        with patch.object(trial.subprocess, "run", return_value=self.result("example", fires=True)):
            code, out = self.cases({"snippet": "-token", "path": "src/a.rs"})
        self.assertEqual(code, 0)
        self.assertIn("fires", out)
        self.assertNotIn("expected", out)

    def test_wrong_expectation_fails(self) -> None:
        with patch.object(trial.subprocess, "run", return_value=self.result("example", fires=True)):
            code, out = self.cases({"snippet": "token", "path": "src/a.rs", "fires": False})
        self.assertEqual(code, 1)
        self.assertIn("expected quiet, got fires", out)

    def test_rejects_patch_envelopes_in_labelled_cases(self) -> None:
        for snippet in ("[src/a.rs#AAAA]\n+ token", "*** Begin Patch\n+ token", "*** Update File: src/a.rs",
                        "*** Add File: src/a.rs", "token\nPUT >3:\n+ token", "CUT 2*=3"):
            with self.subTest(snippet=snippet), patch.object(trial.subprocess, "run", return_value=self.result("example")):
                code, out = self.cases({"snippet": snippet, "path": "src/a.rs", "fires": False})
                self.assertNotEqual(code, 0)
                self.assertIn("a rule case is what the matcher sees: the added lines of one file", str(code) + out)

    def test_one_bad_case_does_not_stop_the_others(self) -> None:
        with patch.object(trial.subprocess, "run", return_value=self.result("example", fires=True)):
            code, out = self.cases({"snippet": "[a.rs#AAAA]", "path": "src/a.rs", "fires": True},
                                   {"snippet": "token", "path": "src/a.rs", "fires": True})
        self.assertEqual(code, 1)
        self.assertIn("1/1 passed", out)
        self.assertIn("1 case(s) could not be tested", out)

    def test_only_exact_single_file_deliveries_are_scored(self) -> None:
        verdicts = iter([True, False, True, True])
        with patch.object(trial.subprocess, "run",
                          side_effect=lambda *a, **k: self.result("example", fires=next(verdicts))):
            code, out = self.cases(
                {"snippet": "[pasted#AAAA]\ntoken", "path": "src/a.rs", "delivered": ["example"], "delivery": "exact"},
                {"snippet": "token", "path": "src/b.rs", "delivered": ["example"], "delivery": "exact"},
                {"snippet": "token", "path": "src/c.rs", "delivered": [], "delivery": "exact"},
                {"snippet": "token", "path": "src/d.rs", "delivered": [], "delivery": "batch"})
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("DIFF"), 2)
        self.assertIn("(live batch: quiet)", out)
        self.assertIn("offline agrees with live delivery on 1/3 single-file edits", out)

    def test_judged_rules_are_not_scored_against_live_delivery(self) -> None:
        self.rule.write_text("---\ncondition: token\nquestion: is it bad?\n---\n")
        with patch.object(trial.subprocess, "run", return_value=self.result("example", fires=True)):
            code, out = self.cases({"snippet": "token", "path": "src/a.rs", "delivered": [], "delivery": "exact"})
        self.assertEqual(code, 0, out)
        self.assertNotIn("DIFF", out)
        self.assertNotIn("agrees", out)

    def test_edit_and_write_cases_require_path(self) -> None:
        for tool in ("edit", "write"):
            with self.subTest(tool=tool), patch.object(trial.subprocess, "run", return_value=self.result("example")):
                code, out = self.cases({"snippet": "other", "tool": tool, "fires": False})
                self.assertNotEqual(code, 0)
                self.assertIn("requires path", str(code) + out)


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
