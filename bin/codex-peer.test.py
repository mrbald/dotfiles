#!/usr/bin/env python3
"""Offline contract tests for codex-peer. Run: python3 bin/codex-peer.test.py"""

import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

PEER = Path(__file__).resolve().with_name("codex-peer")
GOOD_BRIEF = "Review the diff. Please call no other model.\n"


def message(text):
    return {"type": "item.completed", "item": {"type": "agent_message", "text": text}}


def stream(*events):
    return "".join(json.dumps(event) + "\n" for event in events)


class PeerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-peer-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("GIT_") and k != "CODEX_PEER_GUARD"}
        subprocess.run(["git", "init", "-q", str(self.repo)], env=self.env, check=True)
        self.brief = self.root / "brief with spaces.md"
        self.brief.write_text(GOOD_BRIEF)
        self.out = self.root / "out with spaces"
        self.seen = self.root / "seen"
        self.events = self.root / "events"
        self.events.write_text(stream({"type": "thread.started", "thread_id": "t-9"},
                                      message("ok")))
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "codex"
        stub.write_text(f"#!{sys.executable}\n" + '''import json, os, sys, time
from pathlib import Path
Path(os.environ["SEEN"]).write_text(json.dumps({
    "args": sys.argv[1:], "brief": sys.stdin.read(),
    "cache": os.environ.get("UV_CACHE_DIR")}))
if os.environ.get("BLOCK_OUTPUT"):
    Path(os.environ["BLOCK_OUTPUT"]).mkdir()
sys.stdout.buffer.write(Path(os.environ["EVENTS"]).read_bytes())
sys.stdout.buffer.flush()
print("stub stderr", file=sys.stderr, flush=True)
time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
sys.exit(int(os.environ.get("STUB_STATUS", "0")))
''')
        stub.chmod(0o755)
        # Exercise macOS wrapping without invoking the host power-management tool.
        for name, body in {
            "uname": 'printf "%s\\n" "$STUB_OS"\n',
            "caffeinate": 'echo "$1" > "$CAFFEINATED"\nshift\nexec "$@"\n',
        }.items():
            path = bin_dir / name
            path.write_text("#!/bin/sh\n" + body)
            path.chmod(0o755)
        self.env.update(PATH=f"{bin_dir}:{os.environ['PATH']}", SEEN=str(self.seen),
                        EVENTS=str(self.events), STUB_OS="Linux",
                        CAFFEINATED=str(self.root / "caffeinated"),
                        GIT_CEILING_DIRECTORIES=str(self.root))

    def peer(self, *extra, seconds="60", cwd=None, env=None, args=None):
        return subprocess.run(
            ["sh", str(PEER), *(args if args is not None else
              ["gpt-x", str(self.brief), str(self.out), seconds, *extra])],
            cwd=cwd or self.repo, env=env or self.env,
            capture_output=True, text=True, timeout=15,
        )

    def saved(self, suffix):
        return Path(str(self.out) + suffix)

    def test_refusals(self):
        for args, seconds, expected in [
            (["m", "brief"], "60", "usage:"),
            (None, "0", "above zero"),
            (None, "", "whole number"),
            (None, "-1", "whole number"),
            (None, "1.5", "whole number"),
            (None, "abc", "whole number"),
        ]:
            with self.subTest(args=args, seconds=seconds):
                done = self.peer(args=args, seconds=seconds)
                self.assertEqual(done.returncode, 64, done.stderr)
                self.assertIn(expected, done.stderr)
        for extra in [("--unknown", "x"), ("--resume",),
                      ("--sandbox", "bogus"), ("--effort",)]:
            with self.subTest(extra=extra):
                self.assertEqual(self.peer(*extra).returncode, 64)
        self.brief.unlink()
        self.assertEqual(self.peer().returncode, 64)
        self.brief.write_text("Review the diff.\n")
        done = self.peer()
        self.assertEqual(done.returncode, 64)
        self.assertIn("call no other model", done.stderr)
        self.brief.write_text(GOOD_BRIEF)
        done = self.peer(cwd=self.root)
        self.assertEqual(done.returncode, 65)
        self.assertIn("git repo", done.stderr)
        self.assertFalse(self.seen.exists(), "refusals must not start codex")

    def test_guard_override_and_disable(self):
        self.brief.write_text("Review. -custom [literal].\n")
        env = {**self.env, "CODEX_PEER_GUARD": "-custom [literal]"}
        self.assertEqual(self.peer(env=env).returncode, 0)
        env["CODEX_PEER_GUARD"] = "absent"
        self.seen.unlink()
        done = self.peer(env=env)
        self.assertEqual(done.returncode, 64)
        self.assertIn("absent", done.stderr)
        self.assertFalse(self.seen.exists())
        env["CODEX_PEER_GUARD"] = ""
        self.assertEqual(self.peer(env=env).returncode, 0)

    def test_fresh_and_resume_arguments_every_mode(self):
        modes = ("read-only", "workspace-write", "danger-full-access", "containers")
        for mode in modes:
            for resume in (False, True):
                with self.subTest(mode=mode, resume=resume):
                    extra = ["--sandbox", mode]
                    if resume:
                        extra += ["--resume", "t-9"]
                    done = self.peer(*extra)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    expected = ["exec"] + (["resume", "t-9"] if resume else [])
                    if not resume and mode != "containers":
                        expected += ["--sandbox", mode]
                    expected += ["--json", "-m", "gpt-x", "-c",
                                 f'model_reasoning_effort="{"high" if resume else "xhigh"}"']
                    if mode == "containers":
                        expected += ["-c", 'default_permissions="codex-peer-containers"',
                                     "-c", 'permissions.codex-peer-containers.extends=":workspace"',
                                     "-c", "permissions.codex-peer-containers.network.enabled=true"]
                    elif resume:
                        expected += ["-c", f'sandbox_mode="{mode}"']
                    record = json.loads(self.seen.read_text())
                    self.assertEqual(record["args"], expected + ["-"])
                    self.assertEqual(record["brief"], GOOD_BRIEF)
                    if mode == "containers":
                        self.assertTrue(record["cache"].startswith("/tmp/"))
                    self.assertEqual(done.stdout.splitlines(), ["t-9", str(self.out) + ".md"])
                    self.assertEqual(self.saved(".md").read_text(), "ok\n")
                    self.assertEqual(self.saved(".err").read_text(), "stub stderr\n")
                    self.assertEqual(self.saved(".jsonl").read_text(), self.events.read_text())
        self.assertFalse((self.root / "caffeinated").exists())

    def test_defaults_effort_and_caffeinate(self):
        done = self.peer()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(self.seen.read_text())["args"],
                         ["exec", "--sandbox", "read-only", "--json", "-m", "gpt-x",
                          "-c", 'model_reasoning_effort="xhigh"', "-"])
        for extra in [[], ["--resume", "t-9"]]:
            done = self.peer(*extra, "--effort", "medium", env={**self.env, "STUB_OS": "Darwin"})
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn('model_reasoning_effort="medium"', json.loads(self.seen.read_text())["args"])
        self.assertEqual((self.root / "caffeinated").read_text(), "-i\n")

    def test_extract_last_message_and_first_thread(self):
        self.events.write_text(stream(
            {"type": "thread.started", "thread_id": "t-1"}, message("first"),
            {"type": "thread.started", "thread_id": "t-later"},
            {"item": {"type": "command_execution", "text": "x"}},
            message("second\nline"), message(None), {"type": "turn.completed"}
        ) + 'not json\n[]\nnull\n')
        done = self.peer("--resume", "fallback")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.saved(".thread").read_text(), "t-1\n")
        self.assertEqual(self.saved(".md").read_text(), "second\nline\n")

    def test_extract_fallback_and_no_thread(self):
        self.events.write_text(stream(message("again")))
        done = self.peer("--resume", "t-3")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines()[0], "t-3")
        self.assertEqual(self.saved(".thread").read_text(), "t-3\n")
        done = self.peer()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines()[0], "")
        self.assertFalse(self.saved(".thread").exists())

    def test_no_message_clears_stale_files(self):
        for events in [stream({"type": "thread.started", "thread_id": "t-2"}), ""]:
            with self.subTest(events=events):
                self.saved(".md").write_text("earlier round\n")
                self.saved(".thread").write_text("stale\n")
                self.events.write_text(events)
                done = self.peer()
                self.assertEqual(done.returncode, 70, done.stderr)
                self.assertIn("no agent message", done.stderr)
                self.assertFalse(self.saved(".md").exists())
                if events:
                    self.assertEqual(self.saved(".thread").read_text(), "t-2\n")
                else:
                    self.assertFalse(self.saved(".thread").exists())

    def test_failure_keeps_incomplete_message(self):
        done = self.peer(env={**self.env, "STUB_STATUS": "142"})
        self.assertEqual(done.returncode, 71, done.stderr)
        self.assertIn("codex exited 142", done.stderr)
        self.assertIn("incomplete", done.stderr)
        self.assertEqual(self.saved(".md").read_text(), "ok\n")
        self.events.write_text("")
        self.assertEqual(self.peer(env={**self.env, "STUB_STATUS": "1"}).returncode, 71)
        self.assertFalse(self.saved(".md").exists())

    def test_out_starting_with_dash(self):
        out = "-review"
        for suffix in (".md", ".thread"):
            (self.repo / (out + suffix)).write_text("stale\n")
        done = self.peer(args=["gpt-x", str(self.brief), out, "60"])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.repo / (out + ".md")).read_text(), "ok\n")
        self.assertEqual((self.repo / (out + ".thread")).read_text(), "t-9\n")

    def test_cleanup_failure_aborts_before_codex(self):
        # A directory cannot be unlinked by rm -f, even when run as root.
        self.saved(".thread").mkdir()
        done = self.peer()
        self.assertEqual(done.returncode, 71, done.stderr)
        self.assertIn("cannot remove stale outputs", done.stderr)
        self.assertFalse(self.seen.exists())
        self.assertFalse(self.saved(".jsonl").exists())

    def test_cleanup_failure_preserves_stale_writable_file(self):
        self.saved(".thread").write_text("stale\n")
        # Simulate denied directory unlink while the existing file stays writable.
        rm = self.root / "bin" / "rm"
        rm.write_text("#!/bin/sh\nexit 1\n")
        rm.chmod(0o755)
        done = self.peer()
        self.assertEqual(done.returncode, 71, done.stderr)
        self.assertFalse(self.seen.exists())
        self.assertEqual(self.saved(".thread").read_text(), "stale\n")

    def test_missing_python_or_perl(self):
        # Only selected tools are on PATH, so host installations cannot mask absence.
        tools = ("sh", "codex", "python3", "perl", "git", "grep", "rm", "uname")
        for missing in ("python3", "perl"):
            with self.subTest(missing=missing):
                isolated = self.root / ("without-" + missing)
                isolated.mkdir()
                for tool in tools:
                    if tool != missing:
                        target = shutil.which(tool, path=self.env["PATH"])
                        self.assertIsNotNone(target, tool)
                        (isolated / tool).symlink_to(target)
                done = self.peer(env={**self.env, "PATH": str(isolated)})
                self.assertEqual(done.returncode, 71, done.stderr)
                self.assertIn("missing dependency " + missing, done.stderr)
                self.assertFalse(self.seen.exists())

    def test_extraction_failure(self):
        self.events.write_bytes(b"invalid utf-8: \xff\n")
        done = self.peer()
        self.assertEqual(done.returncode, 71, done.stderr)
        self.assertIn("extraction or output-write failure", done.stderr)
        self.assertFalse(self.saved(".md").exists())

    def test_extracted_output_write_failure(self):
        for suffix in (".thread", ".md"):
            with self.subTest(suffix=suffix):
                done = self.peer(env={**self.env, "BLOCK_OUTPUT": str(self.saved(suffix))})
                self.assertEqual(done.returncode, 71, done.stderr)
                self.assertIn("extraction or output-write failure", done.stderr)
                self.saved(suffix).rmdir()

    def test_run_output_write_failure(self):
        for suffix in (".jsonl", ".err"):
            with self.subTest(suffix=suffix):
                self.saved(suffix).mkdir()
                done = self.peer()
                self.assertEqual(done.returncode, 71, done.stderr)
                self.assertFalse(self.seen.exists())
                self.saved(suffix).rmdir()
                for other in (".jsonl", ".err"):
                    self.saved(other).unlink(missing_ok=True)

    def test_alarm_bounds_stub(self):
        done = self.peer(seconds="1", env={**self.env, "STUB_SLEEP": "30"})
        self.assertEqual(done.returncode, 71, done.stderr)
        self.assertIn("incomplete", done.stderr)
        self.assertEqual(self.saved(".md").read_text(), "ok\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
