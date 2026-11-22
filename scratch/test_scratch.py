"""Tests for the session scratch root (plan 0041). Run: python3 -m unittest discover -s scratch

Every test runs a copy of the scripts whose BASE is rewritten to a private temporary folder, so no test
reads or deletes anything under the real /tmp/cs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ("common.sh", "session-start", "scratch-rm", "scratch-sweep")


class ScratchCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="scratch-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        self.base = os.path.join(self.tmp, "cs")
        for name in SCRIPTS:
            with open(os.path.join(HERE, name)) as f:
                text = f.read()
            if name == "common.sh":
                self.assertIn("\nBASE=/tmp/cs\n", text)
                text = text.replace("\nBASE=/tmp/cs\n", f"\nBASE={self.base}\n")
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write(text)
            os.chmod(path, 0o755)
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.home, ".claude", "sessions"))
        self.outside = os.path.join(self.tmp, "outside")
        os.mkdir(self.outside)
        self.victim = os.path.join(self.outside, "keep.txt")
        self.write(self.victim)
        self.sid = str(uuid.uuid4())

    # helpers
    def run_script(self, name: str, *args: str, sid: str | None = None, cwd: str | None = None,
                   extra: dict | None = None) -> subprocess.CompletedProcess:
        env = {"HOME": self.home, "PATH": "/usr/bin:/bin", "CLAUDE_CODE_SESSION_ID": self.sid if sid is None else sid}
        env.update(extra or {})
        return subprocess.run([os.path.join(self.bin, name), *args], env=env, cwd=cwd or self.tmp,
                              capture_output=True, text=True, timeout=30)

    def write(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("x")

    def make_root(self, sid: str | None = None) -> str:
        root = os.path.join(self.base, sid or self.sid)
        os.makedirs(root, mode=0o700)
        os.chmod(self.base, 0o700)
        return root


class SessionStartTest(ScratchCase):
    def test_creates_private_root_and_exports_tmpdir(self) -> None:
        env_file = os.path.join(self.tmp, "env")
        r = self.run_script("session-start", extra={"CLAUDE_ENV_FILE": env_file})
        self.assertEqual(r.returncode, 0, r.stderr)
        root = os.path.join(self.base, self.sid)
        self.assertTrue(os.path.isdir(root))
        self.assertEqual(os.stat(root).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(self.base).st_mode & 0o777, 0o700)
        with open(env_file) as f:
            self.assertEqual(f.read(), f"\nexport TMPDIR={root}/\n")

    def test_tmpdir_takes_effect_for_mktemp(self) -> None:
        env_file = os.path.join(self.tmp, "env")
        self.run_script("session-start", extra={"CLAUDE_ENV_FILE": env_file})
        root = os.path.join(self.base, self.sid)
        # macOS mktemp ignores TMPDIR without a template, so the template form is what sessions must use.
        for cmd in ('mktemp -d "$TMPDIR/x.XXXXXX"', "python3 -I -c 'import tempfile; print(tempfile.mkdtemp())'"):
            out = subprocess.run(["sh", "-c", f". {env_file}; {cmd}"], capture_output=True, text=True, check=True)
            self.assertTrue(os.path.realpath(out.stdout.strip()).startswith(os.path.realpath(root) + "/"), out.stdout)

    def test_second_run_keeps_root(self) -> None:
        env_file = os.path.join(self.tmp, "env")
        self.run_script("session-start", extra={"CLAUDE_ENV_FILE": env_file})
        self.write(os.path.join(self.base, self.sid, "f"))
        r = self.run_script("session-start", extra={"CLAUDE_ENV_FILE": env_file})
        self.assertEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.base, self.sid, "f")))

    def test_bad_id_does_nothing(self) -> None:
        env_file = os.path.join(self.tmp, "env")
        for sid in ("", "../../etc", "not-a-uuid", self.sid.upper()):
            r = self.run_script("session-start", sid=sid, extra={"CLAUDE_ENV_FILE": env_file})
            self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(env_file))

    def test_symlinked_root_is_not_used(self) -> None:
        os.makedirs(self.base, mode=0o700)
        os.chmod(self.base, 0o700)
        os.symlink(self.outside, os.path.join(self.base, self.sid))
        env_file = os.path.join(self.tmp, "env")
        r = self.run_script("session-start", extra={"CLAUDE_ENV_FILE": env_file})
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(env_file))

    def test_without_env_file_still_exits_zero(self) -> None:
        self.assertEqual(self.run_script("session-start").returncode, 0)

    def test_makes_loose_folders_private(self) -> None:
        root = os.path.join(self.base, self.sid)
        os.makedirs(root)
        os.chmod(self.base, 0o777)
        os.chmod(root, 0o777)
        env_file = os.path.join(self.tmp, "env")
        self.run_script("session-start", extra={"CLAUDE_ENV_FILE": env_file})
        self.assertEqual(os.stat(self.base).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(root).st_mode & 0o777, 0o700)
        self.assertTrue(os.path.exists(env_file))

    def test_unterminated_env_file_stays_valid(self) -> None:
        env_file = os.path.join(self.tmp, "env")
        with open(env_file, "w") as f:
            f.write("export A=1")
        self.run_script("session-start", extra={"CLAUDE_ENV_FILE": env_file})
        out = subprocess.run(["sh", "-c", f'. {env_file} && echo "$A $TMPDIR"'], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), f"1 {os.path.join(self.base, self.sid)}/")

    def test_missing_common_exits_zero(self) -> None:
        os.remove(os.path.join(self.bin, "common.sh"))
        self.assertEqual(self.run_script("session-start").returncode, 0)


class ScratchRmTest(ScratchCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.make_root()

    def assert_refused(self, r: subprocess.CompletedProcess) -> None:
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("nothing deleted", r.stderr)
        self.assertTrue(os.path.exists(self.victim))

    def test_deletes_file_and_tree_inside_root(self) -> None:
        f = os.path.join(self.root, "a.txt")
        d = os.path.join(self.root, "tree", "deep")
        self.write(f)
        self.write(os.path.join(d, "x"))
        r = self.run_script("scratch-rm", f, os.path.join(self.root, "tree"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(f))
        self.assertFalse(os.path.exists(os.path.join(self.root, "tree")))
        self.assertTrue(os.path.isdir(self.root))

    def test_relative_path_from_inside_root(self) -> None:
        self.write(os.path.join(self.root, "rel", "x"))
        r = self.run_script("scratch-rm", "rel", cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "rel")))

    def test_missing_path_is_skipped(self) -> None:
        r = self.run_script("scratch-rm", os.path.join(self.root, "gone"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_refuses_the_root_itself(self) -> None:
        for p in (self.root, self.root + "/", self.root + "/.", os.path.join(self.root, "x", "..")):
            self.assert_refused(self.run_script("scratch-rm", p))
        self.assertTrue(os.path.isdir(self.root))

    def test_refuses_dotdot_out(self) -> None:
        self.assert_refused(self.run_script("scratch-rm", os.path.join(self.root, "..", "..", "outside", "keep.txt")))

    def test_refuses_absolute_path_outside(self) -> None:
        self.assert_refused(self.run_script("scratch-rm", self.victim))
        self.assert_refused(self.run_script("scratch-rm", self.outside))

    def test_refuses_another_sessions_root(self) -> None:
        other = self.make_root(str(uuid.uuid4()))
        self.write(os.path.join(other, "f"))
        r = self.run_script("scratch-rm", os.path.join(other, "f"))
        self.assertEqual(r.returncode, 2)
        self.assertTrue(os.path.exists(os.path.join(other, "f")))

    def test_refuses_path_through_symlink_out(self) -> None:
        os.symlink(self.outside, os.path.join(self.root, "link"))
        self.assert_refused(self.run_script("scratch-rm", os.path.join(self.root, "link", "keep.txt")))

    def test_deletes_symlink_not_its_target(self) -> None:
        link = os.path.join(self.root, "link")
        os.symlink(self.outside, link)
        r = self.run_script("scratch-rm", link)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.lexists(link))
        self.assertTrue(os.path.exists(self.victim))

    def test_one_refusal_deletes_nothing(self) -> None:
        f = os.path.join(self.root, "a.txt")
        self.write(f)
        self.assert_refused(self.run_script("scratch-rm", f, self.victim))
        self.assertTrue(os.path.exists(f))

    def test_refuses_options(self) -> None:
        self.write(os.path.join(self.root, "-rf"))
        self.assert_refused(self.run_script("scratch-rm", "-rf", cwd=self.root))
        self.assertEqual(self.run_script("scratch-rm", "./-rf", cwd=self.root).returncode, 0)

    def test_refuses_missing_or_malformed_id(self) -> None:
        for sid in ("", "../..", "x" * 36, self.sid.upper()):
            self.assert_refused(self.run_script("scratch-rm", self.victim, sid=sid))

    def test_ignores_tmpdir(self) -> None:
        self.assert_refused(self.run_script("scratch-rm", self.victim, extra={"TMPDIR": self.outside + "/"}))

    def test_refuses_when_root_is_a_symlink(self) -> None:
        sid = str(uuid.uuid4())
        os.symlink(self.outside, os.path.join(self.base, sid))
        self.assert_refused(self.run_script("scratch-rm", os.path.join(self.base, sid, "keep.txt"), sid=sid))

    def test_refuses_when_root_is_not_private(self) -> None:
        self.write(os.path.join(self.root, "f"))
        for loose, mode in ((self.root, 0o770), (self.base, 0o755)):
            os.chmod(loose, mode)
            r = self.run_script("scratch-rm", os.path.join(self.root, "f"))
            self.assertEqual(r.returncode, 2, loose)
            os.chmod(loose, 0o700)
        self.assertTrue(os.path.exists(os.path.join(self.root, "f")))

    def test_refuses_without_arguments(self) -> None:
        self.assertEqual(self.run_script("scratch-rm").returncode, 2)


class ScratchSweepTest(ScratchCase):
    def age(self, root: str, days: int) -> None:
        old = time.time() - days * 86400
        for dirpath, dirnames, filenames in os.walk(root):
            for n in dirnames + filenames:
                os.utime(os.path.join(dirpath, n), (old, old))
        os.utime(root, (old, old))

    def test_deletes_only_stale_roots_of_ended_sessions(self) -> None:
        stale, fresh, live = (self.make_root(str(uuid.uuid4())) for _ in range(3))
        current = self.make_root()
        for r in (stale, fresh, live, current):
            self.write(os.path.join(r, "f"))
        for r in (stale, live, current):
            self.age(r, 10)
        with open(os.path.join(self.home, ".claude", "sessions", "123.json"), "w") as f:
            f.write('{"pid": 123, "sessionId": "%s"}' % os.path.basename(live))
        self.write(self.victim)
        os.symlink(self.outside, os.path.join(self.base, str(uuid.uuid4())))

        dry = self.run_script("scratch-sweep", "-n")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn(os.path.basename(stale), dry.stdout)
        self.assertTrue(os.path.isdir(stale))

        r = self.run_script("scratch-sweep")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(stale))
        for kept in (fresh, live, current):
            self.assertTrue(os.path.isdir(kept), kept)
        self.assertTrue(os.path.exists(self.victim))

    def test_days_argument(self) -> None:
        root = self.make_root(str(uuid.uuid4()))
        self.write(os.path.join(root, "f"))
        self.age(root, 3)
        self.run_script("scratch-sweep", "7")
        self.assertTrue(os.path.isdir(root))
        self.run_script("scratch-sweep", "2")
        self.assertFalse(os.path.exists(root))
        self.assertEqual(self.run_script("scratch-sweep", "x").returncode, 2)


if __name__ == "__main__":
    unittest.main()
