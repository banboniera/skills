import contextlib
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import sessions


DAY = "2026-01-24"
AFTER = "2026-01-25"
STATUSES = ("completed", "failed", "aborted")


def text(value):
    return {"type": "text", "text": value}


def tool(name, call_id, **arguments):
    return {"type": "toolCall", "name": name, "id": call_id, "arguments": arguments}


def message(role, *content, **meta):
    return {"type": "message", "message": {"role": role, "content": list(content), **meta}}


def result(name, call_id, value="ok", *, error=False, **details):
    return message("toolResult", text(value), toolName=name, toolCallId=call_id,
                   isError=error, details=details)


def delivery(*rules):
    return {"type": "ttsr_injection", "injectedRules": list(rules)}


def custom(custom_type, value, **details):
    return {"type": "custom_message", "customType": custom_type, "content": value,
            "display": False, "details": details, "attribution": "agent"}


def reminder(rule, first_line):
    return f'<system-reminder reason="rule_violation" rule="{rule}" path="rules/{rule}">\n{first_line}\n</system-reminder>'


class SessionsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.project = self.base / "project"
        self.project.mkdir()
        self.root = self.base / "logs"
        self.root.mkdir()
        self.state = self.base / "state"
        self.out = self.base / "digest"
        self.bucket = self.root / f"-tmp-{self.base.name}-project"
        self.name = "2026-01-24T03-04-00-000Z_00000000-0000-0000-0000-000000000001.jsonl"
        environ = patch.dict(os.environ, {"GUIDANCE_SESSIONS": str(self.root),
                                         "GUIDANCE_REVIEW_STATE": str(self.state),
                                         "PI_SESSION_FILE": ""})
        environ.start()
        self.addCleanup(environ.stop)

    def transcript(self, *records, name=None, path=None, cwd=None, day=DAY):
        path = path or self.bucket / (name or self.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        head = {"type": "session", "version": 3, "id": "session-id", "cwd": str(cwd or self.project),
                "timestamp": f"{day}T03:04:00.000Z"}
        prev = None
        with path.open("w") as f:
            f.write(json.dumps({"type": "title"}).ljust(255) + "\n")
            f.write(json.dumps(head) + "\n")
            for i, item in enumerate(records, 1):
                row = {"id": f"e{i}", "parentId": prev, "timestamp": f"{day}T03:04:{i:02d}.000Z", **item}
                f.write(json.dumps(row) + "\n")
                prev = row["id"]
        return path

    def cli(self, *args, ok=True):
        proc = subprocess.run([sys.executable, sessions.__file__, *map(str, args)], cwd=self.project,
                              text=True, capture_output=True)
        if ok:
            self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def digest(self, *args, out=None, default=True):
        out = out or self.out
        cli = (["--since", DAY, "--until", AFTER] if default else []) + ["--out", out, *args]
        proc = self.cli(*cli)
        self.assertTrue((out / "index.json").exists(), "digest did not write index.json")
        index = json.loads((out / "index.json").read_text())
        rows = [json.loads(line) for path in sorted(out.glob("*.events.jsonl"))
                for line in path.read_text().splitlines()]
        return index, rows, proc.stdout

    def test_repeated_multi_rule_delivery_counts_and_pruned_details(self):
        alpha, beta = "always-test", "keep-case"
        self.transcript(
            message("user", text("Consider a change.")),
            custom("ttsr-injection", "[shaken]", rules=[alpha, beta], matched={alpha: "needle"}),
            delivery(),
            custom("ttsr-injection", reminder(alpha, "Rule judge flagged this output.")),
            delivery(alpha),
            message("assistant", text("The change is ready.")),
        )
        index, rows, stdout = self.digest()
        events = [row for row in rows if row["kind"] == "RULE"]
        self.assertEqual([event["data"]["rules"] for event in events], [[alpha, beta], [alpha]])
        self.assertEqual([event["data"]["mode"] for event in events], ["unknown", "judged"])
        self.assertEqual(events[0]["data"]["matched"], {alpha: "needle"})
        self.assertEqual(index["sessions"][0]["deliveries"], {alpha: {"unknown": 1, "judged": 1}, beta: {"unknown": 1}})
        self.assertEqual(index["deliveries"][alpha]["sessions"], 1)
        self.assertEqual(len(index["deliveries"][alpha]["examples"]), 2)
        self.assertIn("rule deliveries", stdout)
        self.assertIn("deliberate reads", stdout)

    def test_custom_interrupt_with_only_rule_attributes(self):
        self.transcript(custom("ttsr-injection", '<system-interrupt reason="rule_violation" rule="guard">\n'
                               'Matched: "bad"\n</system-interrupt>'), delivery())
        _, rows, _ = self.digest()
        self.assertEqual(rows[0]["data"], {"rules": ["guard"], "mode": "interrupt", "matched": {"guard": "bad"}})

    def test_unrelated_branches_do_not_enrich_rules_or_calls(self):
        self.transcript(message("assistant", tool("write", "a", path="x", content="value")),
                        delivery("guard"), result("write", "a"),
                        {**message("developer", text(reminder("guard", "Matched: \"bad\""))), "parentId": "e1"})
        _, rows, _ = self.digest()
        self.assertEqual(next(row for row in rows if row["kind"] == "RULE")["data"]["mode"], "unknown")

    def test_cases_use_one_digest_per_path_and_reminder_belongs_to_batch(self):
        edit = ("*** Begin Patch\n[a.py#A1B2]\nPUT 1.=1:\n++counter\n+\n"
                "[b.py#C3D4]\nPUT 2.=2:\n+print('seen')\n"
                "[a.py#A1B2]\nPUT >5:\n+tail\n*** End Patch")
        path = self.transcript(
            message("user", text("Edit both files.")),
            message("assistant", tool("edit", "a", input=edit), tool("write", "b", path="c.py", content="z")),
            delivery("first"), result("edit", "a"), delivery("second"), result("write", "b"),
            message("developer", text(reminder("first", 'Matched: "seen"')), text(reminder("second", "No match text"))),
            message("assistant", tool("edit", "c", path="d.py", old_string="x", new_string="y")),
            result("edit", "c"),
            message("assistant", text("Done.")),
        )
        self.transcript(message("assistant", tool("write", "s", path="e.py", content="child")),
                        path=path.with_suffix("") / "Scout.jsonl")
        _, rows, _ = self.digest()
        self.assertEqual([row["data"]["mode"] for row in rows if row["kind"] == "RULE"], ["tool-reminder"] * 2)
        output = self.base / "cases.json"
        self.cli("cases", "--since", DAY, "--until", AFTER, "--out", output)
        cases = json.loads(output.read_text())["rule_cases"]
        self.assertEqual([(c["path"], c["snippet"], c["delivered"]) for c in cases], [
            ("a.py", "+counter\n\ntail", ["first", "second"]),
            ("b.py", "print('seen')", ["first", "second"]),
            ("c.py", "z", ["first", "second"]), ("d.py", "y", []), ("e.py", "child", []),
        ])
        self.assertEqual(cases[0], {"path": "a.py", "snippet": "+counter\n\ntail", "source": "tool", "tool": "edit",
                                    "agent": "main", "transcript": str(path), "line": 4, "entry": "e2",
                                    "delivered": ["first", "second"], "delivery": "batch"})
        self.assertEqual([c["delivery"] for c in cases], ["batch", "batch", "batch", "exact", "exact"])
        self.assertEqual(cases[-1]["agent"], "Scout")
        filtered = self.base / "delivered.json"
        self.cli("cases", "--since", DAY, "--until", AFTER, "--delivered", "second", "--out", filtered)
        self.assertEqual(json.loads(filtered.read_text())["rule_cases"], cases[:3])
        globbed = self.base / "globbed.json"
        self.cli("cases", "--since", DAY, "--until", AFTER, "--path", "*.py", "--path", "nope/**", "--out", globbed)
        self.assertEqual(len(json.loads(globbed.read_text())["rule_cases"]), 5)
        narrowed = self.base / "narrowed.json"
        self.cli("cases", "--since", DAY, "--until", AFTER, "--path", "[ab].py", "--out", narrowed)
        self.assertEqual([c["path"] for c in json.loads(narrowed.read_text())["rule_cases"]], ["a.py", "b.py"])
        self.assertEqual(stat.S_IMODE(narrowed.stat().st_mode), 0o600)

    def test_cases_never_overwrite_an_existing_file_or_symlink(self):
        self.transcript(message("user", text("Edit.")), message("assistant", tool("write", "a", path="x.py", content="y")),
                        result("write", "a"))
        existing = self.base / "existing.json"
        existing.write_text("keep")
        target = self.base / "target.txt"
        target.write_text("keep")
        link = self.base / "link.json"
        link.symlink_to(target)
        for output in (existing, link):
            with self.subTest(output=output.name):
                self.assertEqual(self.cli("cases", "--since", DAY, "--until", AFTER, "--out", output,
                                          ok=False).returncode, 2)
        self.assertEqual((existing.read_text(), target.read_text()), ("keep", "keep"))

    def test_cases_skip_internal_urls(self):
        self.transcript(message("user", text("Note it.")),
                        message("assistant", tool("write", "a", path="local://notes.md", content="x"),
                                tool("write", "b", path="src/x.py", content="y")),
                        result("write", "a"), result("write", "b"))
        output = self.base / "cases.json"
        self.cli("cases", "--since", DAY, "--until", AFTER, "--out", output)
        self.assertEqual([c["path"] for c in json.loads(output.read_text())["rule_cases"]], ["src/x.py"])

    def test_user_context_and_end_keep_full_text_and_coordinates(self):
        path = self.transcript(message("user", text("Before")), message("assistant", text("A reply.")),
                               {"type": "model_change", "model": "provider/sample"},
                               message("user", text("Steer\nnow"), steering=True),
                               message("assistant", text("Final\nreply.")))
        index, rows, _ = self.digest()
        self.assertEqual([r["kind"] for r in rows], ["USER", "AGENT", "MODEL", "USER", "END"])
        self.assertEqual(rows[-2]["text"], "(mid-run) Steer\nnow")
        self.assertEqual(rows[-1], {"kind": "END", "line": 7, "stamp": f"{DAY}T03:04:05.000Z",
                                    "entry": "e5", "parent": "e4", "actor": "main", "text": "Final\nreply.", "data": {}})
        summary = index["sessions"][0]
        self.assertEqual(summary["user_turns"], 2)
        self.assertEqual(summary["transcript"], str(path))
        display = (self.out / summary["digest"]).read_text()
        self.assertTrue(display.startswith(f"# {path}\n\n## {DAY}\n"))
        self.assertRegex(display, r"(?m)^03:04:05 L7 END\s+Final reply\.$")
        self.assertEqual(summary["lines"], len(display.splitlines()))
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in self.out.iterdir()))

    def test_single_turn_and_final_subagent_reply_are_reported(self):
        main = self.transcript(message("user", text("One request.")), message("assistant", text("Main answer.")))
        child = self.transcript(message("assistant", text("Child answer.")), path=main.with_suffix("") / "Scout.jsonl")
        index, rows, _ = self.digest()
        self.assertEqual(index["sessions"][0]["subagents"], 1)
        self.assertEqual([(row["actor"], row["text"], row.get("file")) for row in rows if row["kind"] == "END"],
                         [("main", "Main answer.", None), ("Scout", "Child answer.", str(child))])
        self.assertIn(f"### Scout\n\n## {DAY}", next(self.out.glob("*.md")).read_text())

    def test_loads_pair_with_results_and_distinguish_origin(self):
        self.transcript(
            message("assistant", tool("read", "a", path="rule://guard;skill://sample/SKILL.md"),
                    tool("read", "b", path="skill://sample/refs/syntax.txt:4-8"),
                    tool("read", "c", path="skill://sample/refs"),
                    tool("read", "d", path="skill://unknown")),
            result("read", "b", "Not found", error=True),
            result("read", "a", "Skill and rule bodies"),
            result("read", "c", "[Directory: /work/skills/sample/refs]\nsyntax.txt"),
            {**custom("skill-prompt", "Invoked text", name="sample", prompt="Use /skill:sample here."),
             "attribution": "user"},
            message("user", text("Autoloaded text\n\n---\n\nSkill: /work/skills/operator/SKILL.md"),
                    synthetic=True, attribution="agent"),
        )
        index, rows, _ = self.digest()
        self.assertEqual([r["data"] for r in rows if r["kind"] == "LOAD"], [
            {"targets": ["rule://guard", "skill://sample/SKILL.md"], "sub": "body", "outcome": "ok"},
            {"targets": ["skill://sample/refs/syntax.txt"], "sub": "file", "outcome": "failed"},
            {"targets": ["skill://sample/refs"], "sub": "listing", "outcome": "ok"},
            {"targets": ["skill://unknown"], "sub": "body", "outcome": "no-result"},
            {"targets": ["skill://sample"], "sub": "invoked", "outcome": "ok"},
            {"targets": ["skill://operator"], "sub": "autoload", "outcome": "ok"},
        ])
        self.assertEqual([r["text"] for r in rows if r["kind"] == "USER"], ["Use /skill:sample here."])
        self.assertEqual(index["sessions"][0]["reads"], {"rule://guard": 1, "skill://sample": 2})

    def test_failed_checks_and_task_statuses_preserve_result_text(self):
        body = "a" * 220
        tags = "\n".join(f'<task-result id="Worker{i}" agent="task" status="{status}">\n'
                         f'<output>\n{body}\n</output>\n</task-result>' for i, status in enumerate(STATUSES))
        self.transcript(message("assistant", tool("bash", "a", command="check")),
                        result("bash", "a", "Linter error", error=True, exitCode=7),
                        custom("async-result", f"&lt;system-notice>\n{tags}\n</system-notice>",
                               jobs=[{"type": "task", "jobId": f"Worker{i}", "agentId": f"Worker{i}", "status": s}
                                     for i, s in enumerate(STATUSES)]))
        _, rows, _ = self.digest()
        self.assertEqual(rows[0]["kind"], "CHECK")
        self.assertEqual(rows[0]["data"]["tool"], "bash")
        self.assertEqual(rows[0]["data"]["exit_code"], 7)
        self.assertIn("Linter error", rows[0]["text"])
        self.assertEqual([(r["data"]["status"], r["data"]["result"]) for r in rows if r["kind"] == "TASK"],
                         [(status, body[:200]) for status in STATUSES])

    def test_wait_reports_each_settlement_once_and_ignores_running_tasks(self):
        snapshot = [{"id": "Worker", "type": "task", "status": "completed", "settledAtMs": 100, "resultText": "First."},
                    {"id": "Running", "type": "task", "status": "running"},
                    {"id": "Shell", "type": "bash", "status": "completed", "resultText": "Not a task."}]
        self.transcript(result("wait", "a", jobs=snapshot), result("wait", "b", jobs=snapshot),
                        result("wait", "c", jobs=[{**snapshot[0], "settledAtMs": 200, "resultText": "Second."}]))
        _, rows, _ = self.digest()
        self.assertEqual([r["data"]["result"] for r in rows], ["First.", "Second."])

    def test_guidance_edit_advisor_gate_abort_error_compaction_and_model(self):
        self.transcript(message("assistant", tool("edit", "a", path="AGENTS.md", new_string="guidance")),
                        result("edit", "a", "bad", error=True),
                        custom("advisor", '<advisory severity="warning">A note.</advisory>'),
                        custom("session-stop-continuation", "A gate."),
                        message("assistant", stopReason="aborted", errorMessage="Interrupted by user"),
                        message("assistant", stopReason="error", errorMessage="A failure."),
                        {"type": "compaction", "summary": "A summary.", "tokensBefore": 100},
                        {"type": "model_change", "model": "provider/sample"})
        _, rows, _ = self.digest()
        self.assertEqual([r["kind"] for r in rows], ["EDIT", "CHECK", "ADVISOR", "GATE", "ABORT", "ERROR", "COMPACT", "MODEL"])
        self.assertIn("AGENTS.md", rows[0]["text"])
        self.assertIn("A summary.", rows[-2]["text"])
        self.assertIn("provider/sample", rows[-1]["text"])

    def test_match_reads_beyond_preview_and_session_can_have_no_user_in_window(self):
        self.transcript({**message("user", text("Outside.")), "timestamp": "2026-01-23T03:04:01.000Z"},
                        message("assistant", text("x" * 720 + " a-needle-at-the-end")))
        index, rows, _ = self.digest("--match", "a-needle-at-the-end")
        self.assertEqual(index["sessions"][0]["user_turns"], 0)
        self.assertEqual([row["kind"] for row in rows], ["END"])
        self.assertNotIn("a-needle-at-the-end", next(self.out.glob("*.md")).read_text())
        self.assertIn("a-needle-at-the-end", rows[0]["text"])
        self.assertEqual(index["match"], "a-needle-at-the-end")

    def test_exclude_running_and_other_buckets_before_opening(self):
        passed = self.transcript(message("assistant", text("Kept.")))
        excluded = self.transcript(message("assistant", text("Excluded.")), name="excluded.jsonl")
        running = self.transcript(message("assistant", text("Running.")), name="running.jsonl")
        other = self.transcript(message("assistant", text("Other.")), path=self.root / "-somewhere-else" / "other.jsonl")
        self.transcript(message("assistant", text("Wrong cwd.")), name="mismatch.jsonl", cwd=self.base)
        real_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if path in {excluded, running, other}:
                self.fail(f"opened {path}")
            return real_open(path, *args, **kwargs)

        with contextlib.chdir(self.project), patch.object(Path, "open", guarded_open), \
                patch.dict(os.environ, {"PI_SESSION_FILE": str(running)}), contextlib.redirect_stdout(io.StringIO()):
            argv = [sessions.__file__, "digest", "--exclude", "excluded*", "--since", DAY, "--until", AFTER,
                    "--out", str(self.out)]
            with patch.object(sys, "argv", argv):
                sessions.main()
        index = json.loads((self.out / "index.json").read_text())
        self.assertEqual([r["transcript"] for r in index["sessions"]], [str(passed)])
        self.assertEqual(index["excludes"], ["excluded*"])

    def test_root_precedence_and_relative_paths(self):
        self.transcript(message("assistant", text("Kept.")))
        self.assertEqual(self.digest()[0]["sessions_root"], str(self.root))
        with patch.dict(os.environ, {"GUIDANCE_SESSIONS": "../absent"}):
            self.assertEqual(self.digest("--sessions", "../logs", out=self.base / "second")[0]["sessions_root"], str(self.root))
        agent_dir = self.base / "agent"
        with patch.dict(os.environ, {"GUIDANCE_SESSIONS": "", "PI_CODING_AGENT_DIR": "../agent"}):
            self.assertEqual(self.digest(out=self.base / "third")[0]["sessions_root"], str(agent_dir / "sessions"))
        with patch.dict(os.environ, {"GUIDANCE_SESSIONS": "", "PI_CODING_AGENT_DIR": "", "HOME": str(self.base)}):
            self.assertEqual(self.digest(out=self.base / "fourth")[0]["sessions_root"], str(self.base / ".omp/agent/sessions"))

    def test_project_includes_git_worktrees_and_descendant_buckets(self):
        def git(*args):
            subprocess.run(["git", "-C", self.project, *args], check=True, capture_output=True)

        git("init", "-q")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "fixture", "--allow-empty")
        worktree = self.base / "worktree"
        git("worktree", "add", "-q", "--detach", str(worktree))
        child = self.project / "sub"
        child.mkdir()
        sibling_path = self.transcript(message("assistant", text("From worktree")),
                                       path=self.root / f"-tmp-{self.base.name}-worktree" / "worktree.jsonl", cwd=worktree)
        child_path = self.transcript(message("assistant", text("From child dir")),
                                     path=self.root / f"{self.bucket.name}-sub" / "child.jsonl", cwd=child)
        index, _, _ = self.digest("--project", self.project)
        self.assertEqual({row["transcript"] for row in index["sessions"]}, {str(sibling_path), str(child_path)})

    def test_record_advances_only_unfiltered_windows_without_gaps(self):
        self.transcript(message("assistant", text("Kept.")))
        index, _, _ = self.digest()
        self.cli("record", self.out)
        key = f"{self.project}\n{self.root.resolve()}"
        checkpoint = self.state / (hashlib.sha256(key.encode()).hexdigest() + ".json")
        recorded = json.loads(checkpoint.read_text())
        self.assertEqual({k: recorded[k] for k in ("project", "since", "until", "sessions")},
                         {"project": str(self.project), "since": index["since"], "until": index["until"], "sessions": 1})
        self.assertEqual(stat.S_IMODE(checkpoint.stat().st_mode), 0o600)
        self.assertIsNotNone(datetime.fromisoformat(recorded["recorded_at"]).tzinfo)
        implicit, _, stdout = self.digest(out=self.base / "implicit", default=False)
        self.assertEqual(implicit["since"], recorded["until"])
        self.assertIn("recorded", stdout)
        empty = self.base / "other-history"
        empty.mkdir()
        for flags, diagnostic in [(("--match", "Kept"), "match"), (("--exclude", "unused*"), "exclude"),
                                  (("--project", self.project), "project"),
                                  (("--project", self.project, "--project", self.project), "project"),
                                  (("--until", "2099-01-01"), "end by now"),
                                  (("--sessions", empty), "session history")]:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory(dir=self.base) as refuse:
                self.digest(*flags, out=Path(refuse))
                failure = self.cli("record", refuse, ok=False)
                self.assertEqual(failure.returncode, 2)
                self.assertIn(diagnostic, failure.stderr)
        gap = self.base / "gap"
        self.digest("--since", "2026-01-26", "--until", "2026-01-27", default=False, out=gap)
        failure = self.cli("record", gap, ok=False)
        self.assertEqual(failure.returncode, 2)
        self.assertIn("gap", failure.stderr)
        self.assertEqual(json.loads(checkpoint.read_text()), recorded)
        other = self.base / "profile-b"
        other.mkdir()
        with patch.dict(os.environ, {"GUIDANCE_SESSIONS": str(other)}):
            _, _, stdout = self.digest(out=self.base / "profile-b-digest", default=False)
        self.assertIn("no recorded review: last 14 days", stdout)

    def test_quoted_future_marker_does_not_set_checkpoint(self):
        now = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
        marker = f"guidance-review-window 2026-01-24T00:00:00Z 2099-01-24T00:00:00Z {self.project}"
        self.transcript(message("assistant", text(f"`{marker}`")), day=now)
        index, _, stdout = self.digest(default=False)
        self.assertIn("no recorded review: last 14 days", stdout)
        self.assertLess(index["since"], now)
        self.assertEqual(len(index["sessions"]), 1)
        self.assertNotIn("report line", stdout)

    def test_cli_rejects_nonempty_output_and_project_without_since(self):
        self.out.mkdir()
        (self.out / "existing").touch()
        self.assertEqual(self.cli("--out", self.out, ok=False).returncode, 2)
        self.assertEqual(self.cli("--project", self.project, ok=False).returncode, 2)
        with contextlib.ExitStack() as clean:
            proc = self.cli("--since", DAY, "--until", AFTER)
            default = Path(next(row for row in proc.stdout.splitlines() if row.startswith("digests:")).split(":", 1)[1].strip())
            clean.callback(default.rmdir)
            clean.callback((default / "index.json").unlink, missing_ok=True)
            self.assertEqual(stat.S_IMODE(default.stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
