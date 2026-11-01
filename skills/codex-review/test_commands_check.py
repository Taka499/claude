"""Tests for commands_check.py. Run: python3 -m unittest discover -s skills/codex-review"""
import os
import tempfile
import unittest

import commands_check as cc


def record(command, cwd, status=" succeeded in 3ms:", output="ok"):
    return f"exec\n{command} in {cwd}\n{status}\n{output}\n"


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = os.path.realpath(self.tmp.name)
        self.home = os.path.join(root, "home")
        self.repo = os.path.join(self.home, "Developer", "claude")
        self.snap = os.path.join(root, "codex-review.X", "repo")
        for d in (self.repo, self.snap, os.path.join(self.home, ".claude", "security")):
            os.makedirs(d)
        # The way ~/.claude reaches into the repository: a symlink per skill.
        os.makedirs(os.path.join(self.home, ".claude", "skills"))
        os.symlink(self.repo, os.path.join(self.home, ".claude", "skills", "codex-review"))

    def tearDown(self):
        self.tmp.cleanup()

    def bad(self, text):
        return cc.check(text, self.snap, self.repo, self.home)[1]

    def test_ordinary_review_passes(self):
        text = record('/bin/zsh -lc "git diff origin/master...HEAD && sed -n \'1,80p\' skills/x/SKILL.md 2>/dev/null"', self.snap)
        text += record("/bin/zsh -lc 'for f in plans/a.md plans/b.md; do nl -ba \"$f\"; done'", self.snap)
        self.assertEqual(cc.check(text, self.snap, self.repo, self.home), (2, []))

    def test_multiline_command_stops_at_its_status(self):
        text = record('/bin/zsh -lc "rg -n foo \\\n  skills/x"', self.snap, output="exec\nnot a record")
        n, bad = cc.check(text, self.snap, self.repo, self.home)
        self.assertEqual(n, 2)
        self.assertEqual([why for _, why in bad], [["no status line after the command"]])

    def test_repository_by_absolute_home_and_variable_forms(self):
        for path in (self.repo + "/.git/x", "~/Developer/claude/.git/x", "$HOME/Developer/claude/.git/x",
                     "${HOME}/Developer/claude/.git/x"):
            with self.subTest(path=path):
                why = self.bad(record(f'/bin/zsh -lc "touch {path}"', self.snap))[0][1]
                self.assertEqual(why, [f"names the repository: {path}"])

    def test_climbing_out_of_the_snapshot_to_the_repository(self):
        up = os.path.relpath(self.repo, self.snap)
        why = self.bad(record(f'/bin/zsh -lc "git -C {up} stash create"', self.snap))[0][1]
        self.assertEqual(why, [f"names the repository: {up}"])

    def test_a_symlink_into_the_repository(self):
        why = self.bad(record('/bin/zsh -lc "touch ~/.claude/skills/codex-review/x"', self.snap))[0][1]
        self.assertEqual(why, ["names the repository: ~/.claude/skills/codex-review/x"])

    def test_the_plugin_log(self):
        why = self.bad(record('/bin/zsh -lc "echo x >> ~/.claude/security/log.txt"', self.snap))[0][1]
        self.assertEqual(why, ["names the plugin's log: ~/.claude/security/log.txt"])

    def test_ran_outside_the_snapshot(self):
        why = self.bad(record('/bin/zsh -lc "git stash create"', self.repo))[0][1]
        self.assertEqual(why, [f"ran outside the snapshot, in {self.repo}"])

    def test_other_variable_and_outside_paths_fail_closed(self):
        why = self.bad(record('/bin/zsh -lc "cat $TMPDIR/x /etc/hosts .."', self.snap))[0][1]
        self.assertEqual(why, ["a path through a variable: $TMPDIR/x", "a path outside the snapshot: /etc/hosts",
                               "a path outside the snapshot: .."])

    def test_unexpected_shapes_fail_closed(self):
        self.assertEqual(cc.check("", self.snap, self.repo, self.home), (0, []))
        why = self.bad("exec\n/bin/zsh -lc \"git diff\"\n succeeded in 1ms:\n")[0][1]
        self.assertEqual(why, ["no working directory"])

    def test_paths_attached_to_a_prefix(self):
        up = os.path.relpath(self.repo, self.snap)
        for token in (f"file://{self.repo}/x", f"file://localhost{self.repo}/x", f"-o{self.repo}/x",
                      f"-C{up}", "-o~/Developer/claude/x", f"--output{self.repo}/x", f"@{self.repo}/x",
                      f"localhost:{self.repo}/x", f"+{self.repo}/x", f"-o./{up}/x", f"@./{up}/x"):
            with self.subTest(token=token):
                why = self.bad(record(f'/bin/zsh -lc "curl -T payload {token}"', self.snap))[0][1]
                self.assertEqual(why, [f"names the repository: {token}"])

    def test_ordinary_tokens_with_slashes_or_tildes_pass(self):
        text = record('/bin/zsh -lc "git log HEAD~1 && git show HEAD:skills/x && git diff origin/master...HEAD '
                      '&& rg -n https://github.com/a/b skills"', self.snap)
        self.assertEqual(self.bad(text), [])

    def test_quotes_and_backslashes_do_not_hide_a_path(self):
        esc = self.repo.replace("/", "\\/")
        half = '"/"' + self.repo[1:]
        for token in (esc, half):
            with self.subTest(token=token):
                text = record("/bin/zsh -lc '" + "touch " + token + "/x'", self.snap)
                why = self.bad(text)[0][1]
                self.assertEqual(why, [f"names the repository: {self.repo}/x"])

    def test_a_script_that_will_not_split_fails_closed(self):
        why = self.bad(record('/bin/zsh -lc "echo \'unbalanced"', self.snap))[0][1]
        self.assertEqual(why, ["the command will not parse as `<shell> -lc <script>`"])

    def test_a_record_with_no_status_line_fails_closed(self):
        text = f'exec\n/bin/zsh -lc "git diff" in {self.snap}\n'
        self.assertEqual(self.bad(text)[0][1], ["no status line after the command"])

    def test_main_exit_status(self):
        log = os.path.join(self.tmp.name, "review.txt")
        for text, want in (("", 1), (record('/bin/zsh -lc "git diff"', self.snap), 0),
                           (record('/bin/zsh -lc "touch ~/Developer/claude/x"', self.snap), 1)):
            with open(log, "w") as f:
                f.write(text)
            old = os.environ.get("HOME")
            os.environ["HOME"] = self.home
            try:
                self.assertEqual(cc.main(["x", log, self.snap, self.repo]), want)
            finally:
                os.environ["HOME"] = old
        self.assertEqual(cc.main(["x", os.path.join(self.tmp.name, "none"), self.snap, self.repo]), 2)


if __name__ == "__main__":
    unittest.main()
